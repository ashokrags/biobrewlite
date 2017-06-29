import luigi, yaml, saga, os, jsonpickle, time, subprocess, copy, sys
from sqlalchemy.orm import sessionmaker
import biobrewliteutils.catalog_base as cb
from biobrewliteutils.catalog import *
from collections import OrderedDict
import biobrewliteutils.wrappers as wr


class BaseTask:
    def setup(self):
        self.parms = jsonpickle.decode(self.prog_parms[0])
        self.jobparms = self.parms.job_parms
        self.jobparms['workdir'] = self.parms.cwd

        ## Hack to get the command to work for now
        self.jobparms['command'] = '#SBATCH -vvvv\n echo $PATH\n'
        self.jobparms['command'] += self.parms.conda_command + "\n"

        # self.jobparms['command'] +='source activate cbc_conda\n'
        self.jobparms['command'] += 'srun '
        self.jobparms['command'] += self.parms.run_command + "\n"
        self.jobparms['command'] += "srun --cpus-per-task=1 --time=1 echo 'DONE' > " + self.parms.luigi_target

        prog_name = self.parms.name.replace(" ", "_")
        self.name = self.parms.input + "_" + prog_name
        ## Replace class name to be reflected in the luigi visualizer
        ##self.__class__.__name__ = self.name

        self.jobparms['out'] = os.path.join(self.parms.log_dir, self.name + "_mysagajob.stdout")
        self.jobparms['error'] = os.path.join(self.parms.log_dir, self.name + "_mysagajob.stderr")
        self.jobparms['outfilesource'] = 'ssh.ccv.brown.edu:' + self.parms.luigi_target
        self.jobparms['outfiletarget'] = '' + os.path.dirname(self.parms.luigi_local_target) + "/"
        print self.jobparms
        return

    def create_saga_job(self, **kwargs):
        ctx = saga.Context("ssh")
        ctx.user_id = "aragaven"

        session = saga.Session()
        session.add_context(ctx)
        # describe our job
        jd = saga.job.Description()
        jd.executable = ''
        jd.arguments = [kwargs.get('command')]  # cmd
        jd.working_directory = kwargs.get('work_dir', os.getcwd())
        jd.wall_time_limit = kwargs.get('time', 60)
        jd.total_physical_memory = kwargs.get('mem', 2000)
        jd.number_of_processes = 1
        jd.processes_per_host = 1
        jd.total_cpu_count = kwargs.get('ncpus', 1)
        jd.output = kwargs.get('out', os.path.join(jd.working_directory, "mysagajob.stdout"))
        jd.error = kwargs.get('error', "mysagajob.stderr")
        host = kwargs.get('saga_host', 'localhost')
        scheduler = kwargs.get('saga_scheduler', 'fork')
        js = saga.job.Service(scheduler + "://" + host, session=session)
        myjob = js.create_job(jd)
        # Now we can start our job.
        # print " \n ***** SAGA: job Started ****\n"
        myjob.run()

        myjob.wait()
        # print " \n ***** SAGA: job Done ****\n"
        # print kwargs.get('outfilesource')
        # out = saga.filesystem.File(kwargs.get('outfilesource'), session=session)
        # print kwargs.get('outfiletarget')
        # out.copy(kwargs.get('outfiletarget'))
        # subprocess.call(' '.join(['ssh ', host+server] ))
        subprocess.call(' '.join(['scp ', kwargs.get('outfilesource'), kwargs.get('outfiletarget')]), shell=True)
        # print "\n **** SAGA: copy Done ***** \n"
        # out.close()
        js.close()
        return


class TopTask(luigi.Task, BaseTask):
    prog_parms = luigi.ListParameter()

    def run(self):
        self.setup()
        self.__class__.__name__ = str(self.name)
        job = self.create_saga_job(**self.jobparms)
        return

    def output(self):
        self.setup()
        self.__class__.__name__ = str(self.name)
        if self.parms.local_target:
            # lcs.RemoteFileSystem("ssh.ccv.brown.edu").get( self.parms.luigi_target,self.parms.luigi_local_target)
            return luigi.LocalTarget(self.parms.luigi_local_target)
        else:
            return luigi.LocalTarget(self.parms.luigi_target)


class TaskSequence(luigi.Task, BaseTask):
    prog_parms = luigi.ListParameter()

    def requires(self):
        self.setup()
        newParms = [x for x in self.prog_parms]
        del newParms[0]
        if len(newParms) > 1:
            return TaskSequence(prog_parms=newParms)
        else:
            return TopTask(prog_parms=newParms)

    def run(self):
        self.setup()
        self.__class__.__name__ = str(self.name)
        job = self.create_saga_job(**self.jobparms)
        return

    def output(self):
        self.setup()
        self.__class__.__name__ = str(self.name)
        if self.parms.local_target:
            # lcs.RemoteFileSystem("ssh.ccv.brown.edu").get( self.parms.luigi_target,self.parms.luigi_local_target)
            return luigi.LocalTarget(self.parms.luigi_local_target)
        else:
            return luigi.LocalTarget(self.parms.luigi_target)


class TaskFlow(luigi.WrapperTask):
    tasks = luigi.ListParameter()
    task_name = luigi.Parameter()
    task_namespace = "BioProject"

    def requires(self):
        for x in self.tasks:
            yield jsonpickle.decode(x)

    def task_id_str(self):
        return self.task_name


class BaseWorkflow:
    def __init__(self, parmsfile):
        self.parse_config(parmsfile)
        self.prog_wrappers = {'feature_counts': wr.BedtoolsCounts,
                              'gsnap': wr.Gsnap,
                              'fastqc': wr.FastQC,
                              'qualimap_rnaseq': wr.QualiMapRnaSeq,
                              'samtomapped': wr.SamToMappedBam,
                              'samtounmapped': wr.SamToUnmappedBam,
                              'samindex': wr.SamIndex,
                              'samsort': wr.SamToolsSort,
                              'samdup': wr.BiobambamMarkDup
                              }
        self.job_params = {'work_dir': self.run_parms['work_dir'],
                           'time': 80,
                           'mem': 3000
                           }
        self.session = None
        self.main_table = None
        return

    """A shortcut for calling the BaseWrapper __init__ from a subclass."""
    init = __init__

    """
       Parse the YAML file and create workflow class attributes accordingly.
    """

    def parse_config(self, fileHandle):
        for k, v in yaml.safe_load(open(fileHandle, 'r')).iteritems():
            setattr(self, k, v)
        return

    def create_catalog(self):
        engine = create_engine(self.run_parms['db'] + ":///" + self.run_parms['db_loc'])  # , echo=True)
        cb.Base.metadata.create_all(engine, checkfirst=True)
        Session = sessionmaker(bind=engine)
        self.session = Session()
        return


class RnaSeqFlow(BaseWorkflow):
    sample_fastq = dict()
    sample_fastq_work = dict()
    progs = OrderedDict()
    allTasks = []
    progs_job_parms = dict()
    base_kwargs = dict()


    def __init__(self, parmsfile):
        self.init(parmsfile)
        if 'saga_host' in self.run_parms.keys():
            self.job_params['saga_host'] = self.run_parms['saga_host']
        if 'saga_user' in self.run_parms.keys():
            self.job_params['ssh_user'] = self.run_parms['ssh_user']
        if 'saga_scheduler' in self.run_parms.keys():
            self.job_params['saga_scheduler'] = self.run_parms['saga_scheduler']
        self.paired_end = False
        self.parse_sample_info()
        self.setup_paths()
        self.set_base_kwargs()
        self.create_catalog()
        return

    def parse_sample_info(self):
        """
        Read in the sample attributes from file as a dictionary with
        the sample id as the key
        :return: 
        """
        for line in open(self.sample_manifest['fastq_file'], 'r'):
            tmpline = line.strip('\n').split(',')
            # print tmpline[0], tmpline[1]
            self.sample_fastq[tmpline[0]] = []
            self.sample_fastq[tmpline[0]].append(tmpline[1])
            if len(tmpline) > 2:
                self.sample_fastq[tmpline[0]].append(tmpline[2])
                self.paired_end = True
        return

    def parse_prog_info(self):
        """
        Read in the sequence of programs to be run for the current workflow
         and their specified parameters
        :return: 
        """
        for k, v in self.workflow_sequence.iteritems():
            self.progs[k] = []
            print k, v
            if isinstance(v, dict):
                # Add the specific program options
                if 'options' in v.keys():
                    for k1, v1 in v['options'].iteritems():
                        self.progs[k].append("%s %s" % (k1, v1))
                else:
                    self.progs[k].append('')
                # Add the specific program job parameters
                if 'job_params' in v.keys():
                    self.progs_job_parms[k] = v['job_params']
                else:
                    self.progs_job_parms[k] = 'default'
            elif v == 'default':
                self.progs[k].append(v)

                    # self.progs[k].append(v1)
        self.progs = OrderedDict(reversed(self.progs.items()))
        return

    def symlink_fastqs_local(self):
        """
        Create symlinks to the original fastqs locally renaming with given sample ids using the os module
        :return: 
        """
        for samp, fileName in self.sample_fastq.iteritems():
            self.sample_fastq_work[samp] = []
            if len(fileName) < 2:
                symlnk_name = os.path.join(os.path.dirname(fileName[0]), samp + ".fq.gz")
                os.symlink(symlnk_name, fileName)
                self.sample_fastq_work[samp].append(symlnk_name)
            else:
                num = 1
                for file in fileName:
                    symlnk_name = os.path.join(os.path.dirname(file), samp + "_" + num + ".fq.gz")
                    os.symlink(symlnk_name, file)
                    self.sample_fastq_work[samp].append(symlnk_name)
                    num += 1
        return

    def check_paths(self, path, remote=False):
        """
        Check if the directory exists, remote and local, using the saga module.
        :param path: 
        :param remote: 
        :return: 
        """
        if remote:
            session = saga.Session()
            ctx = saga.Context("ssh")
            ctx.user_id = self.run_parms['ssh_user']
            session.add_context(ctx)
            try:
                dir = saga.filesystem.Directory(path, session=session)
            except:
                print os.path.dirname(path)
                dir = saga.filesystem.Directory(os.path.dirname(path))
                dir.make_dir(os.path.basename(path))
                dir.close()
        else:
            if not os.path.exists(path):
                os.mkdir(path)
        return

    def setup_paths(self):
        self.work_dir = self.run_parms['work_dir']
        self.log_dir = os.path.join(self.work_dir, self.run_parms['log_dir'])
        self.checkpoint_dir = os.path.join(self.work_dir, 'checkpoints')
        self.fastq_dir = os.path.join(self.work_dir, 'fastq')
        self.align_dir = os.path.join(self.work_dir, 'alignments')
        self.expression_dir = os.path.join(self.work_dir, 'expression')
        self.qc_dir = os.path.join(self.work_dir, 'qc')
        return

    def test_paths(self):
        paths_to_test = [self.work_dir, self.log_dir, self.checkpoint_dir,
                         self.fastq_dir, self.align_dir, self.expression_dir, self.qc_dir]
        remote_dirs_flag = False
        if self.run_parms['saga_host'] != "localhost":
            remote_dirs_flag = True
            remote_prefix = "sftp://" + self.run_parms['saga_host']
            paths_to_test = [remote_prefix + "/" + x for x in paths_to_test]
            print paths_to_test

        for p in paths_to_test:
            self.check_paths(p, remote_dirs_flag)

        return

    def symlink_fastqs(self):
        """
        Create soft links to original fastqs by renaming, local or remote, using the given sample IDs and the saga module
        :return: 
        """
        # command list
        cmds = []
        # cmds = ''

        remote_dirs = False

        # Add commands to the command list

        for samp, fileName in self.sample_fastq.iteritems():
            self.sample_fastq_work[samp] = []
            if len(fileName) < 2:
                symlnk_name = os.path.join(self.fastq_dir, samp + ".fq.gz")
                # cmds.append(' '.join(['/bin/ln', '-s', fileName[0], symlnk_name]))
                cmds.append(' '.join(['/bin/ln', '-s', fileName[0], symlnk_name, "; echo DONE:", fileName[0], ">> "]))
                self.sample_fastq_work[samp].append(symlnk_name)
            else:
                num = 1
                for fq_file in fileName:
                    symlnk_name = os.path.join(self.fastq_dir, samp + "_" + str(num) + ".fq.gz")
                    # cmds.append(' '.join(['/bin/ln','-s', fq_file, symlnk_name]))
                    cmds.append(' '.join(['/bin/ln', '-s', fq_file, symlnk_name, "; echo DONE:", fq_file, ">> "]))
                    self.sample_fastq_work[samp].append(symlnk_name)
                    num += 1
        print cmds

        # setup remote session

        remote_path = self.run_parms['work_dir']

        if self.run_parms['saga_host'] != "localhost":
            session = saga.Session()
            ctx = saga.Context("ssh")
            ctx.user_id = self.run_parms['ssh_user']
            session.add_context(ctx)
            remote_dirs = True
            remote_path = "sftp://" + self.run_parms['saga_host'] + self.run_parms['work_dir']

        # setup basic job parameters

        jd = saga.job.Description()
        jd.executable = ''
        jd.working_directory = self.run_parms['work_dir']
        # jd.output = os.path.join(log_dir, "symlink.stdout")
        # jd.error = os.path.join(log_dir, "symlink.stderr")
        job_output = os.path.join(self.log_dir, "symlink.stdout")
        job_error = os.path.join(self.log_dir, "symlink.stderr")



        # Setup the saga host to use

        js = saga.job.Service("fork://localhost")
        if self.run_parms['saga_host'] != "localhost":
            js = saga.job.Service("ssh://" + self.run_parms['saga_host'], session=session)

        # Submit jobs

        jobs = []
        for cmd in cmds:
            jd.arguments = cmd + job_output
            myjob = js.create_job(jd)
            myjob.run()
            jobs.append(myjob)
        print ' * Submitted %s. Output will be written to: %s' % (myjob.id, job_output)

        # Wait for all jobs to finish

        while len(jobs) > 0:
            for job in jobs:
                jobstate = job.get_state()
                print ' * Job %s status: %s' % (job.id, jobstate)
                if jobstate in [saga.job.DONE, saga.job.FAILED]:
                    jobs.remove(job)
            print ""
            time.sleep(5)
        js.close()
        return

    def set_base_kwargs(self):
        self.base_kwargs['cwd'] = self.work_dir
        self.base_kwargs['align_dir'] = self.align_dir
        self.base_kwargs['qc_dir'] = self.qc_dir
        self.base_kwargs['conda_command'] = self.run_parms.get('conda_command', 'source activate cbc_conda_test')
        self.base_kwargs['job_parms'] = self.job_params
        self.base_kwargs['job_parms_type'] = "default"
        self.base_kwargs['add_job_parms'] = None
        self.base_kwargs['log_dir'] = self.log_dir
        self.base_kwargs['paired_end'] = self.run_parms.get('paired_end', 'False')
        self.base_kwargs['local_targets'] = self.run_parms.get('local_targets', False)
        self.base_kwargs['luigi_local_path'] = self.run_parms.get('luigi_local_path', os.getcwd())
        self.base_kwargs['gtf_file'] = self.run_parms.get('gtf_file', None)
        self.base_kwargs['genome_file'] = self.run_parms.get('genome_file', None)
        return

    def chain_commands(self):
        """
        Create a n ordered list of commands to be run sequentially for each sample for use with the Luigi scheduler.
        :return: 
        """

        for samp, file in self.sample_fastq_work.iteritems():
            print "\n *******Commands for Sample:%s ***** \n" % (samp)
            samp_progs = []

            for key in self.progs.keys():

                if key == 'gsnap':

                    # Add additional samtools processing steps to GSNAP output

                    tmp_prog = self.prog_wrappers['samdup']('bammarkduplicates2', samp,
                                                            stdout=os.path.join(self.log_dir, samp + '_bamdup.log'),
                                                            **dict(self.base_kwargs)
                                                            )
                    print tmp_prog.run_command

                    samp_progs.append(jsonpickle.encode(tmp_prog))

                    tmp_prog = self.prog_wrappers['samindex']('samtools', samp,
                                                              stdout=os.path.join(self.log_dir, samp + '_bamidx.log'),
                                                              **dict(self.base_kwargs)
                                                              )
                    print tmp_prog.run_command

                    samp_progs.append(jsonpickle.encode(tmp_prog))

                    tmp_prog = self.prog_wrappers['samsort']('samtools', samp,
                                                             stdout=os.path.join(self.log_dir, samp + '_bamsrt.log'),
                                                             **dict(self.base_kwargs)
                                                             )
                    print tmp_prog.run_command

                    samp_progs.append(jsonpickle.encode(tmp_prog))

                    tmp_prog = self.prog_wrappers['samtomapped']('samtools', samp,
                                                                 stdout=os.path.join(self.log_dir,
                                                                                     samp + '_samtobam.log'),
                                                                 **dict(self.base_kwargs)
                                                                 )
                    print tmp_prog.run_command

                    samp_progs.append(jsonpickle.encode(tmp_prog))

                    tmp_prog = self.prog_wrappers['samtounmapped']('samtools', samp,
                                                                   stdout=os.path.join(self.log_dir,
                                                                                       samp + '_samtounmappedbam.log'),
                                                                   **dict(self.base_kwargs)
                                                                   )
                    print tmp_prog.run_command

                    samp_progs.append(jsonpickle.encode(tmp_prog))

                    new_base_kwargs = self.update_job_parms(key)

                    tmp_prog = self.prog_wrappers[key](key, samp, *self.progs[key],
                                                       stdout=os.path.join(self.align_dir, samp + '.sam'),
                                                       **dict(new_base_kwargs))

                    print tmp_prog.run_command

                    samp_progs.append(jsonpickle.encode(tmp_prog))

                else:
                    # print "\n**** Base kwargs *** \n"
                    # print self.base_kwargs
                    tmp_prog = self.prog_wrappers[key](key, samp,
                                                       stdout=os.path.join(self.run_parms['work_dir'],
                                                                           self.run_parms['log_dir'],
                                                                           samp + '_' + key + '.log'),
                                                       **dict(self.base_kwargs)
                                                       )
                    print tmp_prog.run_command
                    samp_progs.append(jsonpickle.encode(tmp_prog))
                    # print self.job_params
                    # tmp_prog.job_parms['mem'] = 1000
                    # tmp_prog.job_parms['time'] = 80
                    # tmp_prog.job_parms['ncpus'] = 1
                    ## Need to fix to read in options and parms

            # Remove the first job and re-add it without any targets

            # del samp_progs[-1]
            # tmp_prog = self.prog_wrappers[key](key, samp,
            #                                    stdout=os.path.join(self.log_dir,samp + '_' + key + '.log'),
            #                                    **dict(self.base_kwargs)
            #                                    )
            # tmp_prog.luigi_source = "None"
            # samp_progs.append(jsonpickle.encode(tmp_prog))
            # print "\n**** Command after removal *** \n"
            # print tmp_prog.run_command
            # for k,v in tmp_prog.__dict__.iteritems():
            #     print k,v
            # # print self.job_params
            # # print tmp_prog.job_parms
            # print tmp_prog.luigi_source
            # self.allTasks.append(TaskSequence(samp_progs))
            self.allTasks.append(jsonpickle.encode(TaskSequence(samp_progs)))
            #print self.allTasks

        return

    def update_job_parms(self, key):

        new_base_kwargs = copy.deepcopy(self.base_kwargs)
        if self.progs_job_parms[key] != 'default':
            new_base_kwargs['job_parms_type'] = "custom"
            new_base_kwargs['add_job_parms'] = self.progs_job_parms[key]
        return new_base_kwargs

if __name__ == '__main__':
    # parmsfile = "/home/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run_remote_tdat.yaml"
    parmsfile = sys.argv[1]
    rw1 = RnaSeqFlow(parmsfile)
    #
    # print "\n***** Printing config Parsing ******\n"
    # for k, v in rw1.__dict__.iteritems():
    #     print k, v
    #     #
    #
    # print "\n***** Printing Sample Info ******\n"
    # for k, v in rw1.sample_fastq.iteritems():
    #     print k, v
    #
    rw1.parse_prog_info()
    # print "\n***** Printing Progs dict ******\n"
    # for k, v in rw1.progs.iteritems():
    #     print k, v
    #
    # rev_progs = OrderedDict(reversed(rw1.progs.items()))
    # print "\n***** Printing Progs dict in reverse ******\n"
    # for k, v in rev_progs.iteritems():
    #     print k, v

    print "\n***** Printing Chained Commands ******\n"

    # Actual jobs start here
    rw1.test_paths()
    rw1.symlink_fastqs()
    rw1.chain_commands()
    luigi.build([TaskFlow(tasks=rw1.allTasks, task_name=rw1.bioproject)], local_scheduler=True,
                workers=len(rw1.sample_fastq_work.keys()), lock_size=1)
    # luigi.build([TaskFlow(tasks=rw1.allTasks)], local_scheduler=False, workers=2, lock_size=3)
    # luigi.build(self.rw1.allTasks, local_scheduler=False, workers=3, lock_size=3)
