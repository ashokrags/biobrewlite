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
A series of wrappers for external calls to various bioinformatics tools.
"""

import glob
import math
import operator
import os
import random
import shlex
import subprocess
import sys
import copy
import time
import hashlib

from collections import namedtuple
from itertools import chain

# import config
# import diagnostics
import utils


class BaseWrapper:
    """
    A base class that handles generic wrapper functionality.

    Wrappers for specific programs should inherit this class, call `self.init`
    to specify their `name` (which is a key into the executable entries in the
    BioLite configuration file), and append their arguments to the `self.args`
    list.

    By convention, a wrapper should call `self.run()` as the final line in its
    `__init__` function. This allows for clean syntax and use of the wrapper
    directly, without assigning it to a variable name, e.g.

    wrappers.MyWrapper(arg1, arg2, ...)

    When your wrapper runs, BaseWrapper will do the following:

    * log the complete command line to diagnostics;
    * optionally call the program with a version flag (invoked with `version`)
      to obtain a version string, then log this to the :ref:`programs-table`
      along with a hash of the binary executable file;
    * append the command's stderr to a file called `name`.log in the CWD;
    * also append the command's stdout to the same log file, unless you set
      `self.stdout`, in which case stdout is redirected to a file of that name;
    * on Linux, add a memory profiling library to the LD_PRELOAD environment
      variable;
    * call the command and check its return code (which should be 0 on success,
      unless you specify a different code with `self.return_ok`), optionally
      using the CWD specified in `self.cwd` or the environment specified in
      `self.env`.
    * parse the stderr of the command to find [biolite.profile] markers and
      use the rusage values from `utils.safe_call` to populate a profile
      entity in the diagnostics with walltime, usertime, systime, mem, and
      vmem attributes.
    """

    def __init__(self, name, **kwargs):
        self.name = name
        # self.shell = '/bin/sh'
        self.cmd = None
        self.run_command = None
        self.args = []
        self.job_parms = kwargs.get('job_parms')
        self.paired_end = kwargs.get('paired_end',False)
        self.cwd = kwargs.get('cwd', os.getcwd())
        self.log_dir = kwargs.get('log_dir', "logs")
        self.luigi_source = os.path.join(self.cwd, kwargs.get('source', "None"))
        self.luigi_target = os.path.join(self.cwd, kwargs.get('target', "None"))

        ## Below for testing only
        self.local_target =kwargs.get('local_target',True)
        self.luigi_local_target = os.path.join(kwargs.get('luigi_local_path',"/Users/aragaven/scratch/test_workflow"),
                                               kwargs.get('target',"None"))

        self.stdout = kwargs.get('stdout')
        self.stdout_append = kwargs.get('stdout_append')
        # self.pipe = kwargs.get('pipe')
        self.env = os.environ.copy()
        self.max_concurrency = kwargs.get('max_concurrency', 1)
        self.prog_args = dict()
        for k,v in kwargs.iteritems():
            self.prog_args[k] = v
        self.setup_command()
        # self.output_patterns = None

    init = __init__
    """A shortcut for calling the BaseWrapper __init__ from a subclass."""

    # def check_input(self, flag, path):
    #     """
    #     Turns path into an absolute path and checks that it exists, then
    #     appends it to the args using the given flag (or None).
    #     """
    #     path = os.path.abspath(path)
    #     if os.path.exists(path):
    #         if flag:
    #             self.args.append(flag)
    #         self.args.append(path)
    #     else:
    #         utils.die("input file for flag '%s' does not exists:\n  %s" % (flag, path))

    def add_threading(self, flag):
        """
        Indicates that this wrapper should use threading by appending an
        argument with the specified `flag` followed by the number of threads
        specified in the BioLite configuration file.
        """
        # threads = min(int(config.get_resource('threads')), self.max_concurrency)
        threads = self.max_concurrency
        if threads > 1:
            self.args.append(flag)
            self.args.append(threads)

    def add_openmp(self):
        """
        Indicates that this wrapper should use OpenMP by setting the
        $OMP_NUM_THREADS environment variable equal to the number of threads
        specified in the BioLite configuration file.
        """
        ##threads = min(int(config.get_resource('threads')), self.max_concurrency)
        threads = self.max_concurrency
        self.env['OMP_NUM_THREADS'] = str(threads)

    def setup_command(self):
        """
        Generate the command to be run based on the input. There are three cases and more can defined based on the YAML
        1) Just a name is given and this is also the executable name and is available in the PATH
        2) The name is given along-with a separate sub-command to be run. A simple example will be `samtools sort`
         this definition need to be implemented
        :param self: 
        :return: 
        """
        # Setup the command to run

        if not self.cmd:
            self.cmd = [self.name]  # change cmd to be name if specific command is not specified
        else:
            self.cmd = list(self.cmd.split())
        return

    def version(self, flag=None, path=None):
        """
        Generates and logs a hash to distinguish this particular installation
        of the program (on a certain host, with a certain compiler, program
        version, etc.)

        Specify the optional 'binary' argument if the wrapper name is not
        actually the program, e.g. if your program has a Perl wrapper script.
        Set 'binary' to the binary program that is likely to change between
        versions.

        Specify the optional 'cmd' argument if the command to run for version
        information is different than what will be invoked by `run` (e.g.
        if the program has a perl wrapper script, but you want to version an
        underlying binary executable).
        """
        cmd = copy.deepcopy(self.cmd)
        if flag:
            cmd.append(flag)
        else:
            cmd.append('-v')

        # Run the command.
        try:
            vstring = subprocess.check_output(cmd, env=self.env, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            vstring = e.output
        except OSError as e:
            utils.failed_executable(cmd[0], e)

        if not path:
            path = self.env['PATH']

            # Generate a hash.
            # vhash = diagnostics.log_program_version(self.name, vstring, path)
            # if vhash:
            # 	diagnostics.prefix.append(self.name)
            # 	diagnostics.log('version', vhash)
            # 	diagnostics.prefix.pop()

    def version_jar(self):
        """
        Special case of version() when the executable is a JAR file.
        """
        # cmd = config.get_command('java')
        cmd = 'java '
        cmd.append('-jar')
        cmd += self.cmd
        self.version(cmd=cmd, path=self.cmd[0])

    def setup_run(self):
        """
        Call this function at the end of your class's `__init__` function.
        """
        cmd = self.cmd
        stderr = os.path.join(self.cwd,self.log_dir,self.name + '_err.log')
        if len(self.name.split()) > 1:
            stderr = os.path.join(self.cwd, self.log_dir,'_'.join(self.name.split()) + '_err.log')
        self.args.append('2>>' + stderr)

        # if self.pipe:
        # 	self.args += ('|', self.pipe, '2>>' + stderr)

        # Write to a stdout file if it was set by the derived class.
        # Otherwise, stdout and stderr will be combined into the log file.

        if self.stdout:
            stdout = os.path.abspath(self.stdout)
            self.args.append('1>' + stdout)
            # diagnostics.log('stdout', stdout)
        elif self.stdout_append:
            stdout = os.path.abspath(self.stdout_append)
            self.args.append('1>>' + stdout)
            # diagnostics.log('stdout', stdout)
        else:
            self.args.append('1>>' + stderr)

        cmd = ' '.join(chain(cmd, map(str, self.args)))
        self.run_command = cmd + "; echo 'DONE' > " + self.luigi_target

    def run_jar(self, mem=None):
        """
        Special case of run() when the executable is a JAR file.
        """
        # cmd = config.get_command('java')
        cmd = 'java '
        if mem:
            cmd.append('-Xmx%s' % mem)
        cmd.append('-jar')
        cmd += self.cmd
        self.run(cmd)


### Third-party command line tools ###

class FastQC(BaseWrapper):
    """
    A wrapper for FastQC.
    http://www.bioinformatics.bbsrc.ac.uk/projects/fastqc/
    """
    args = []

    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '_fastqc.zip').hexdigest() + ".txt"
        if kwargs.get('paired_end'):
            kwargs['target'] = hashlib.sha224(input + '_2_fastqc.zip').hexdigest() + ".txt"
        self.init(name, **kwargs)
        # self.luigi_source = "None"
        self.version('-v')
        self.add_threading('-t')
        self.args += args
        if self.paired_end:

            self.args.append(os.path.join(self.cwd,input + "_1.fq.gz"))
            self.setup_run()
            run_cmd1 = self.run_command
            self.init(name, **kwargs)
            self.args += args
            self.args.append(os.path.join(self.cwd,input + "_2.fq.gz"))
            self.setup_run()
            run_cmd2 = self.run_command
            self.run_command = run_cmd1 + "; " + run_cmd2
        else:
            self.args.append(os.path.join(self.cwd,input + ".fq.gz"))
            self.setup_run()
        return

class Gsnap(BaseWrapper):
    """
    A wrapper for gsnap 
    
    """

    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '.sam').hexdigest() + ".txt"
        self.init(name, **kwargs)
        if self.paired_end:
            kwargs['source'] = hashlib.sha224(input + '_2_fastqc.gzip').hexdigest() + ".txt"
        else:
            kwargs['source'] = hashlib.sha224(input + '_fastqc.gzip').hexdigest() + ".txt"
        self.setup_args()
        self.args += args
        if self.paired_end:
            self.args.append(os.path.join(self.cwd,input + "_1.fq.gz"))
            self.args.append(os.path.join(self.cwd,input + "_2.fq.gz"))
        else:
            self.args.append(os.path.join(self.cwd,input + ".fq.gz"))
        # self.cmd = ' '.join(chain(self.cmd, map(str, self.args), map(str,input)))
        self.setup_run()
        return

    def setup_args(self):
        self.args += ["--gunzip", "-A sam", "-N1"]
        return


class SamTools(BaseWrapper):
    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        # kwargs['target'] = hashlib.sha224(input + '.fq.gz').hexdigest() + ".txt"
        self.init(name, **kwargs)
        # self.version()
        self.args += args
        self.args.append(input)
        self.setup_run()
        return


class SamToMappedBam(BaseWrapper):
    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '.bam').hexdigest() + ".txt"
        name = name + " view"
        self.init(name, **kwargs)
        self.args = ["-F 0x4","-Sbh ", "-o", os.path.join(self.cwd,input + ".bam")]
        self.args += args
        self.args.append(os.path.join(self.cwd,input + ".sam"))
        self.setup_run()
        return

class SamToUnmappedBam(BaseWrapper):
    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '.unmapped.bam').hexdigest() + ".txt"
        name = name + " view"
        self.init(name, **kwargs)
        self.args = ["-f 0x4", "-Sbh ", "-o", os.path.join(self.cwd,input + ".unmapped.bam")]
        self.args += args
        self.args.append(os.path.join(self.cwd,input + ".sam"))
        self.setup_run()
        return


class SamToolsSort(BaseWrapper):
    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '.srtd.bam').hexdigest() + ".txt"
        name = name + " sort"
        self.init(name, **kwargs)
        self.args = ["-o", os.path.join(self.cwd, input + ".srtd.bam")]
        self.args += args
        self.args.append(os.path.join(self.cwd,input + ".bam"))
        self.setup_run()
        return


class SamIndex(BaseWrapper):
    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '.srtd.bam.bai').hexdigest() + ".txt"
        name = name + " index"
        self.init(name, **kwargs)
        self.args = [os.path.join(self.cwd,input + ".srtd.bam")]
        self.args += args
        self.setup_run()
        return


class BiobambamMarkDup(BaseWrapper):
    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '.dup.srtd.bam').hexdigest() + ".txt"
        self.init(name, **kwargs)
        self.args = ["I=" + os.path.join(self.cwd,input + ".srtd.bam"),
                     "O=" + os.path.join(self.cwd,input + ".dup.srtd.bam"),
                     "M=" + os.path.join(self.cwd,input + ".dup.metrics.txt")]
        self.args += args
        self.setup_run()
        return


class RnaSeqQc(BaseWrapper):
    """
    A wrapper for the GenePattern Module RnaSeqQc

    """

    cmd = ''
    args = []

    def __init__(self, input, *args):
        self.cmd = ['rnaseqc']
        self.args += args
        self.cmd = ' '.join(chain(self.cmd, map(str, self.args), input))
        return


class BedtoolsCounts(BaseWrapper):
    """
    A wrapper for FeatureCounts

    """

    def __init__(self, name, input, *args, **kwargs):
        self.input = input
        kwargs['target'] = hashlib.sha224(input + '.counts.csv').hexdigest() + ".txt"
        name = name + " multicov "
        self.init(name, **kwargs)
        self.args = ["-S ",
                     "O=" + os.path.join(self.cwd, input + ".dup.srtd.bam"),
                     "M=" + os.path.join(self.cwd, input + ".dup.metrics.txt")]
        self.args += args
        self.setup_run()
        return