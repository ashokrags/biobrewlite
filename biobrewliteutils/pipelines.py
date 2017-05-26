# BioLite - Tools for processing gene sequence data and automating workflows
# Copyright (c) 2012-2014 Brown University. All rights reserved.
#
# This file is part of BioLite.
#
# BioLite is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BioLite is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BioLite.  If not, see <http://www.gnu.org/licenses/>.

"""
BioLite borrows from Ruffus (http://code.google.com/p/ruffus/) the idea of
using Python function decorators to delineate pipeline stages. Pipelines are
created with a sequence of ordinary Python functions decorated by a pipeline
object, which registers each function as a *stage* in the pipeline.  The
pipeline object maintains a persistent, global dictionary, called the *state*,
and runs each stage by looking up the argument names in the stage function's
signature, and calling the function with the values in the state dictionary
whose keys match the function's argument names.  This is implemented using the
function inspection methods available from the :mod:`inspect` module in the
Python standard library.  If the stage function returns a dictionary, it is
*ingested* into the pipeline's state by adding values for any new keys and
updating values for existing keys.  Arguments passed on the command-line to the
pipeline script form the initial data in the pipeline's state.

As an example, the following code setups a pipeline with two command-line
arguments and one stage. Note how the variable names in the stage function's
signature match the names of the arguments.  The stage uses the `ingest` call
to pull the `output` path into the pipeline's state. This way, it is accessible
to other stages that might be added to this pipeline.

::

  from biolite.pipeline import BasePipeline
  from biolite.wrappers import FilterIllumina

  pipe = BasePipeline('filter', "Example pipeline")

  pipe.add_argument('input', short='i',
  	help="Input FASTA or FASTQ file to filter.")

  pipe.add_argument('quality', short='q', type=int, metavar='MIN',
  	default=28, help="Filter out reads that have a mean quality < MIN.")

  @pipe.stage
  def filter(input, quality):
  	'''
  	Filter out low-quality and adapter-contaminated reads
  	'''
  	output = input + '.filtered'
  	FilterIllumina([input], [output], quality=quality)
  	ingest('output')

  if __name__ == "__main__":
  	pipe.parse_args()
  	pipe.run()

This script is available in `examples/filter-pipeline.py` and produces the
following help message:

::

  $ python examples/filter-pipeline.py -h
  usage: filter-pipeline.py [-h] [--restart [CHK]] [--stage N] [--input INPUT]
                            [--quality MIN]

  Example pipeline

  optional arguments:
    -h, --help            show this help message and exit
    --restart [CHK]       Restart the pipeline from the last available
                          checkpoint, or from the specified checkpoint file CHK.
    --stage N             Start at stage number N. Note that some stages require
                          the output of previous stages, so starting in the
                          middle of a pipeline may not work.
    --input INPUT, -i INPUT
                          Input FASTA or FASTQ file to filter.
    --quality MIN, -q MIN
                          Filter out reads that have a mean quality < MIN. [28]

  pipeline stages:
    0) [filter]
  	Filter out low-quality and adapter-contaminated reads

The pipeline module allows you to rapidly create full-featured pipeline scripts
with help messages, checkpointing and restart capabilities, and integration
with the BioLite diagnostics and catalog databases (using the `Pipeline` or
`IlluminaPipeline` derived classes).

Meta-Pipelines
--------------

Modularity is a key design goal, and it is possible to reuse one or more stages
of an existing pipeline when building a new pipeline. It is also possible to
build meta-pipelines that connect together several sub-pipelines.

Checkpoints
-----------

The pipeline object also incorporates fault tolerance.  At the end of each
stage, the pipeline stores a *checkpoint* by dumping its current state to a
binary file with the :mod:`cPickle` module. This way, if a run is interrupted,
either due to an internal error or to external conditions, such as a kill
signal from a batch system or a hardware failure, the run can be restarted from
the last completed stage (or, optionally, from any previous stage in the
checkpoint).
"""

import argparse
import cPickle
import inspect
import os
import time

from collections import OrderedDict
from copy import deepcopy

import catalog
import config
import diagnostics
import utils


class BasePipeline:
    """
    BasePipeline is the more generic class. It is designed to be used
    independently of the BioLite diagnostics and catalog features.
    """

    def __init__(self, name, desc=""):
        self.name = name
        self.desc = desc
        self.args = OrderedDict()
        self.stages = list()
        self.nstage = -1
        self.state = dict()
        self.checkpoints = list()
        self.skip = list()

        # Delayed creation of the parser happens in parse_args()
        self.parser = None
        self.parsed_args = dict()

        # Create an url to use for checkpoint filename, etc.
        self.safe_name = utils.safe_str(name)
        self.state['chkfile'] = self.safe_name + '.chk'

        # Add common arguments for all pipelines.
        self.add_arg('--restart', metavar='CHK', nargs='?', help="""
			Restart the pipeline from the last available checkpoint, or from
			the specified checkpoint file CHK.""")

        self.add_arg('--stage', type=int, metavar='N', help="""
			Start at stage number N. Note that some stages require the output
			of previous stages, so starting in the middle of a pipeline may
			not work.""")

        self.add_arg('--skip', type=str, action='append', help="""
			A list of stages and pipelines to skip. Give the names of stages,
			separated by commas, and any of those which are encountered will
			not be run. Given the name of a pipeline, all of the stages in
			that pipeline will not be run. This argument can be specified
			multiple times and the list is concatenated.""")

    def get(self, key):
        return self.state.get(key)

    ### Methods for building meta-pipelines from imported pipelines.

    def import_stages(self, pipe, start=0):
        """
        Imports all the stages from another pipeline, or only those starting
        from number `start`.
        """
        for func in pipe.stages[start:]:
            self.add_stage(func)

    def import_arguments(self, pipe, names=None):
        """
        Import all the arguments from another pipeline, or only the sublist
        from `names`.
        """
        if names is None:
            self.args.update(pipe.args)
        else:
            for name in names:
                self.args[name] = pipe.args[name]

    def import_module(self, module, names=None, start=0):
        """
        Imports another pipeline, adding all of its arguments, or only the
        sublist from `names`, and all of its stages, or only those starting
        from number `start`.
        """
        self.import_arguments(module.pipe, names)
        self.import_stages(module.pipe, start)

    ### This decorator adds stages to the pipeline.

    def stage(self, func):
        """
        Decorator to add functions as stages of this pipeline.
        """
        # Check that input is a function
        if not inspect.isfunction(func):
            utils.info("""
                      The object you have decorated as a stage:
                      %s
                      is not an inspectable Python function.""")
        else:
            self.add_stage(func)
        return func

    def add_stage(self, func):
        self.stages.append(func)
        # Provide references to this pipeline object for ingestion.
        if 'pipeline' not in func.__dict__:
            func.__dict__['pipeline'] = self.safe_name
        func.func_globals['ingest'] = self.ingest

    def list_stages(self):
        lines = ["pipeline stages:"]
        for i in range(0, self.size()):
            f = self.stages[i]
            lines.append(" %2d) [%s] %s" % (i, f.__name__, f.__doc__))
        return '\n'.join(lines)

    def size(self):
        """
        Returns the size of the pipeline (the number of stages it contains).
        """
        return len(self.stages)

    def parse_args(self):
        """
        Reads values passed as arguments into the pipeline's *state*.
        """
        # Create the parser on-the-fly so that we can incorporate the list of
        # stages as the epilog in the auto-generated help message.
        self.parser = argparse.ArgumentParser(
            description=self.desc,
            epilog=self.list_stages(),
            argument_default=argparse.SUPPRESS,
            formatter_class=argparse.RawDescriptionHelpFormatter)

        # All arguments added to the pipeline were cached in 'self.args'.
        for args, kwargs in self.args.values():
            self.parser.add_argument(*args, **kwargs)
        args = vars(self.parser.parse_args())

        if 'stage' in args:
            self.nstage = args.pop('stage')
            if self.nstage >= self.size():
                utils.die("Pipeline has no stage %d" % self.nstage)

        if 'skip' in args:
            self.skip = sum(map(lambda x: x.split(","), args.pop('skip')), [])

        # Restart from a checkpoint, if indicated.
        if 'restart' in args:
            chkfile = args.pop('restart')
            # If a checkpoint file was not specified on the command line, use
            # the default name.
            if not chkfile:
                chkfile = self.state['chkfile']
            self.restart(chkfile)
            self.parsed_args['restart'] = chkfile
            # Prune any arguments with default values that would override the
            # values in the state from the restart.
            for key in self.state:
                if key in args:
                    if args[key] == self.args[key][1].get('default'):
                        args.pop(key)

        for key, val in args.iteritems():
            self.state[key] = val
            self.parsed_args[key] = val

    def add_arg(self, flag, short=None, **kwargs):
        """
        Passes arguments through to the add_argument() method from
        ArgumentParser.
        """
        name = flag.lstrip('-')
        if 'default' in kwargs:
            self.state[name] = kwargs['default']
            # Auto-add default values to the help string.
            kwargs['help'] = str(kwargs.get('help')) + " [%(default)s]"
        # Cache this argument for now: it will be added to the parser
        # when self.parse_args() is called.
        args = [flag]
        if short: args.append(short)
        self.args[name] = (args, kwargs)

    def add_path_arg(self, flag, short=None, **kwargs):
        kwargs['type'] = os.path.abspath
        self.add_arg(flag, short, **kwargs)

    def checkpoint(self):
        """
        Writes checkpoint file by making a deep copy of the pipeline's current
        *state* and pickling it to the value of `chkfile` in the state (by
        default, this is the pipeline's name followed by '.chk' in the current
        working directory).
        """
        # Expand the checkpoint list so it is big enough to accommodate the
        # current stage.
        nchk = len(self.checkpoints)
        if self.nstage >= nchk:
            for _ in range(nchk, self.nstage + 1):
                self.checkpoints.append(dict())
        # Make a deep copy of the current stage's state.
        self.checkpoints[self.nstage] = deepcopy(self.state)
        with open(self.state['chkfile'], 'w') as f:
            cPickle.dump(self.checkpoints, f)

    def restart(self, chkfile):
        """
        Restart the pipeline from the last stage written to the checkpoint
        file `chkfile`, which is unpickled and loaded as the current *state*
        using a deepcopy.
        """
        utils.info("Restarting from checkpoint '%s'" % chkfile)
        with open(chkfile, 'r') as f:
            self.checkpoints = cPickle.load(f)
        # By default (if the current stage is unset), use the latest stage
        # stored in the checkpoint.
        nchk = len(self.checkpoints)
        utils.info("Checkpoint has %d stage(s)" % nchk)
        if self.nstage < 0:
            # Verify the number of stages in the checkpoint.
            if nchk >= len(self.stages):
                utils.die("""
  This checkpoint has already completed the pipeline. To restart from an
  earlier stage in this checkpoint, use the --stage option.""")
            self.nstage = nchk
        elif self.nstage > nchk:
            utils.die("Can't restart at stage %d" % self.nstage)
        # Load the previous stage, since a checkpoint represents a completed
        # stage.
        if self.nstage > 0:
            self.state = deepcopy(self.checkpoints[self.nstage - 1])

    def run(self):
        """
         Starts the pipeline at the stage specified with `--stage`, or at stage
        0 if no stage was specified.
        """
        self.nstage = max(self.nstage, 0)
        utils.info("Starting at stage", self.nstage)
        for s in self.stages[self.nstage:]:
            utils.info("\n  STAGE %d / %s.%s\n  %s" % (
                self.nstage, self.name, s.__name__, s.__doc__))
            if not self.run_stage(s):
                utils.info("\n  (Skipped.)")
            self.nstage += 1

    def run_stage(self, func):
        """
        Runs the current stage (from *self.nstage*) by using the :mod:`inspect`
        module to read the function signature of the decorated stage function,
        then injecting values from the *state* where the key matches the
        variable name in the function signature.
        """
        name = func.__name__
        if name in self.skip or func.__dict__['pipeline'] in self.skip:
            return False
        diagnostics.log("skipped", False)
        argspec = inspect.getargspec(func)
        if argspec.defaults is not None:
            utils.info("""
	  Stage '%s' has an argument with a default value, but this value
	  will be ignored by the pipeline.""")
        argdict = dict()
        for arg in argspec.args:
            if not arg in self.state:
                utils.die("error: argument '%s' is required" % arg)
            else:
                argdict[arg] = self.state[arg]
        ret = func(**argdict)
        # Try to ingest any dictionaries returned by the stage function.
        if ret is not None:
            try:
                self.state.update(ret)
            except ValueError:
                utils.info("""
	  Could not ingest return object from the stage function.
	  It must be a dictionary or a list of (key,val) tuples.""")
        # Checkpoint is created at stage completion.
        self.checkpoint()
        return True

    def ingest(self, *args):
        """
        Called from inside a pipeline stage to ingest values back into the
        pipeline's *state*. It uses the :mod:`inspect` module to get the
        calling functions (i.e. the stage function's) local variable
        dictionary, and copies the variable names specified in the `args`
        list.
        """
        lvars = utils.get_caller_locals()
        for name in args:
            try:
                self.state[name] = lvars[name]
            except KeyError:
                utils.info("""
  Could not ingest variable '%s'
  The list of local variables does not contain that variable name.""" % name)


class Pipeline(BasePipeline):
    """
    Extends BasePipeline to make use of the BioLite diagnostics and catalog
    databases.
    """

    def __init__(self, name, desc=""):
        self.start = time.time()
        self.file = inspect.currentframe().f_back.f_code.co_filename
        BasePipeline.__init__(self, name, desc)
        diagnostics.prefix = [self.safe_name]

        # Command-line arguments.

        self.add_arg('--id', '-i', required=True, type=utils.safe_str, help="""
			BioLite catalog ID of the input sequences.""")

        self.add_arg('--newrun', action='store_true', help="""
			Create a new run ID for this run, even if it is a restart.""")

    def run(self):
        # Parse arguments.
        self.parse_args()

        # Initialize the diagnostics file, used for global logging.
        id = self.state.get('id', None)
        if self.state.pop('newrun', False):
            # Create a new run ID by passing 'None' to init.
            run_id = None
        else:
            # Try to use the previous run ID.
            run_id = self.state.get('_run_id', None)
        self.state['_run_id'] = diagnostics.init(id, self.safe_name, run_id)

        # Load the local diagnostics file into the diagnostics cache,
        # since some pipeline stages may depend on previous diagnotics entries
        # during a restart.
        diagnostics.load_cache()
        diagnostics.prefix = [diagnostics.INIT]
        diagnostics.log_dict(self.parsed_args)
        diagnostics.log_dict(config.resources, 'config.resources')
        diagnostics.log_dict(config.tools, 'config.tools', True)
        diagnostics.log_path(os.getcwd(), 'scratch')
        diagnostics.log_entity('__rusage__.timestamp', self.start)

        self.nstage = max(self.nstage, 0)
        utils.info("Starting at stage", self.nstage)
        for s in self.stages[self.nstage:]:
            diagnostics.prefix = [s.__dict__['pipeline'], s.__name__]
            rusage = diagnostics.log_rusage()
            utils.info("\n  STAGE %d / %s.%s / %.3fs / %.1fMB\n  %s" % (
                self.nstage, s.__dict__['pipeline'], s.__name__,
                rusage['timestamp'] - self.start,
                rusage['maxrss'] / 1024.0, s.__doc__))
            if self.run_stage(s):
                diagnostics.log("skipped", False)
            else:
                diagnostics.log("skipped", True)
                utils.info("\n  (Skipped.)")
            self.nstage += 1

        diagnostics.prefix = [diagnostics.EXIT]
        rusage = diagnostics.log_rusage()
        utils.info("\n  FINISHED / %.3fs / %.1fMB" % (
            rusage['timestamp'] - self.start,
            rusage['maxrss'] / 1024.0))

    # Call this at the end of a pipeline to store the paths to output files,
    # etc. in the diagnostics.
    def finish(self, *args):
        lvars = utils.get_caller_locals()
        # Always log into the current entity of the calling stage.
        # Only log output if this is the final stage.
        if self.nstage == len(self.stages) - 1:
            diagnostics.prefix = [diagnostics.EXIT]
            diagnostics.prefix.append('scratch')
            diagnostics.log_path(os.getcwd())
            diagnostics.prefix.pop()
            for name in args:
                try:
                    diagnostics.log(name, lvars[name])
                except KeyError:
                    utils.info("""
  Could not output final variable '%s'
  The list of local variables does not contain that variable name.""" % name)
        # Otherwise, ingest the values (e.g. in a meta-pipeline when reaching
        # the end of a sub-pipeline).
        else:
            self.state["scratch"] = os.getcwd()
            for name in args:
                try:
                    self.state[name] = lvars[name]
                except KeyError:
                    utils.info("""
  Could not ingest variable '%s'
  The list of local variables does not contain that variable name.""" % name)

    def log_state(self, *names):
        prefix_save = diagnostics.prefix
        diagnostics.prefix = [diagnostics.EXIT]
        for name in names:
            try:
                diagnostics.log(name, self.state[name])
            except KeyError:
                utils.info("no variable '%s' in pipeline state" % name)
        diagnostics.prefix = prefix_save

    # Add hooks for 'finish' and 'log_state'
    def add_stage(self, func):
        BasePipeline.add_stage(self, func)
        func.func_globals['finish'] = self.finish
        func.func_globals['log_state'] = self.log_state


# Initial stage 0 used by IlluminaPipeline.
def setup_data(id, fastq, previous, _data_sources):
    """Setup paths to the FASTQ input sequence data"""

    if fastq:
        data = [fastq]
    else:
        data = diagnostics.lookup_prev_val(
            id, previous, None, "data", *_data_sources)
        if data:
            utils.info("found previous run data", data)
            data = diagnostics.str2list(data)
        else:
            utils.info("reading data from paths in catalog")
            record = catalog.select(id)
            # Split the paths, and make sure there are two.
            try:
                data = [catalog.split_paths(record.paths)]
            except AttributeError:
                utils.die("catalog entry missing for id", id)

                # diagnostics.log("data", data)
    ingest("data")


class IlluminaPipeline(Pipeline):
    """
    An extension of Pipeline that assumes that the input data is a forward and
    reverse FASTQ pair, such as a paired-end Illumina data set.
    """

    def __init__(self, name, desc=""):
        Pipeline.__init__(self, name, desc + """
By default, this pipeline will try to locate the output data of any compatible
pipelines run before it. Alternatively, you can manually specify the input data
using the (--fastq, -f) argument, or manually specify a previous pipeline run
to read from using the (--previous, -p) argument.  Finally, if no data is
available by any of these means, the paths in the catalog will be used as input
data.""")

        # Override the file found by the Pipeline constructor (which is this
        # file, pipeline.py).
        self.file = inspect.currentframe().f_back.f_code.co_filename

        # Command-line arguments.

        self.add_arg('--fastq', '-f', nargs=2, type=os.path.abspath,
                     default=None, help="""
			Manually specify paths to the forward and reverse FASTQ inputs.""")

        self.add_arg('--previous', '-p', nargs='?', metavar='RUN_ID',
                     default=False, help="""
			Use the outputs of a previous pipeline run as inputs.""")

        self.add_arg('--gzip', '-z', action='store_true',
                     default=False, help="""
			Use gzip compression for output files.""")

        # Add setup stage.
        self.add_stage(setup_data)
        self.state["_data_sources"] = []

    # Default to starting imports at index 1, since we always add 'setup_paths'
    # as the 0 stage.
    def import_stages(self, pipe, start=1):
        BasePipeline.import_stages(self, pipe, start)

    def add_data_sources(self, *args):
        self.state["_data_sources"] += args

# vim: noexpandtab ts=4 sw=4
