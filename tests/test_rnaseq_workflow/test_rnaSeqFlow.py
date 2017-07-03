import unittest, saga, luigi
from unittest import TestCase
from definedworkflows.rnaseq.rnaseqworkflow import RnaSeqFlow as rsw
from collections import OrderedDict

from definedworkflows.rnaseq.rnaseqworkflow import TaskFlow
import luigi.contrib.ssh as lcs


class TestRnaSeqFlow(TestCase):
    def setUp(self):
        ##self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run.yaml"
        ##self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run_remote.yaml"
        ##self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run_remote_lapierre_pe.yaml"
        self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run_localhost_slurm.yaml"

        self.rw1 = rsw(self.parmsfile)

    # def test_parse_config(self):
    #     self.rw1.parse_config(self.parmsfile)
    #
    #     print "\n***** Printing config Parsing ******\n"
    #     for k, v in self.rw1.__dict__.iteritems():
    #         print k, v
    #
    def test_parse_sample_info(self):
        self.rw1.parse_sample_info()
        print "\n***** Printing Sample Info ******\n"
        for k, v in self.rw1.sample_fastq.iteritems():
            print k, v
        print self.rw1.paired_end

    def test_parse_prog_info(self):
        self.rw1.parse_prog_info()
        print "\n***** Printing Progs dict ******\n"
        for k, v in self.rw1.progs.iteritems():
            print k, v

        rev_progs = OrderedDict(reversed(self.rw1.progs.items()))
        print "\n***** Printing Progs dict in reverse ******\n"
        for k, v in rev_progs.iteritems():
            print k, v
        for k, v in self.rw1.progs_job_parms.iteritems():
            print k, v

    # def test_symlink_fastqs(self):
    #     #self.rw1.sample_fastq = {'sampN2': ['/gpfs/scratch/aragaven/test_workflow/N1-BC1_AACCAG_R1.fastq.gz'],
    #      #                        'sampN3': ['/gpfs/scratch/aragaven/test_workflow/N3-BC3_AGTGAG_R1.fastq.gz']}
    #     self.rw1.parse_sample_info()
    #     self.rw1.symlink_fastqs()

    def test_chain_commands_se(self):
        self.rw1.sample_fastq_work = {'N2': '/gpfs/scratch/aragaven/test_workflow/sampN2.fq.gz',
                                      'N3': '/gpfs/scratch/aragaven/test_workflow/sampN3.fq.gz'}
        # self.rw1.symlink_fastqs
        self.rw1.set_base_kwargs()
        self.rw1.parse_prog_info()
        print self.rw1.progs
        print "\n***** Printing Chained Commands ******\n"
        self.rw1.set_base_kwargs()
        self.rw1.chain_commands()


        # def test_run_chain_commands(self):
        #     self.rw1.parse_prog_info()
        #     self.rw1.test_paths()
        #     self.rw1.symlink_fastqs()
        #     self.rw1.chain_commands()
        #     luigi.build([TaskFlow(tasks=self.rw1.allTasks, task_name=self.rw1.bioproject)], local_scheduler=False,
        #                 workers=len(self.rw1.sample_fastq_work.keys()), lock_size=1)
        #     # # luigi.build([TaskFlow(tasks=self.rw1.allTasks)], local_scheduler=False, workers=2, lock_size=3)
        #     # luigi.build(self.rw1.allTasks, local_scheduler=False, workers=3, lock_size=3)


class TestRnaSeqFlowLocalHostSE(TestCase):
    def setUp(self):
        self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run_localhost_slurm.yaml"
        self.rw1 = rsw(self.parmsfile)

    def test_parse_config(self):
        self.rw1.parse_config(self.parmsfile)

        print "\n***** Printing config Parsing ******\n"
        for k, v in self.rw1.__dict__.iteritems():
            print k, v

    def test_parse_sample_info(self):
        self.rw1.parse_sample_info()
        print "\n***** Printing Sample Info ******\n"
        for k, v in self.rw1.sample_fastq.iteritems():
            print k, v
        print self.rw1.paired_end

    def test_parse_prog_info(self):
        self.rw1.parse_prog_info()
        print "\n***** Printing Progs dict ******\n"
        for k, v in self.rw1.progs.iteritems():
            print k, v

        rev_progs = OrderedDict(reversed(self.rw1.progs.items()))
        print "\n***** Printing Progs dict in reverse ******\n"
        for k, v in rev_progs.iteritems():
            print k, v
        for k, v in self.rw1.progs_job_parms.iteritems():
            print k, v

    # def test_symlink_fastqs(self):
    #     #self.rw1.sample_fastq = {'sampN2': ['/gpfs/scratch/aragaven/test_workflow/N1-BC1_AACCAG_R1.fastq.gz'],
    #      #                        'sampN3': ['/gpfs/scratch/aragaven/test_workflow/N3-BC3_AGTGAG_R1.fastq.gz']}
    #     self.rw1.parse_sample_info()
    #     self.rw1.symlink_fastqs()

    def test_chain_commands_se(self):
        self.rw1.sample_fastq_work = {'N2': '/gpfs/scratch/aragaven/test_workflow/sampN2.fq.gz',
                                      'N3': '/gpfs/scratch/aragaven/test_workflow/sampN3.fq.gz'}
        # self.rw1.symlink_fastqs
        self.rw1.set_base_kwargs()
        self.rw1.parse_prog_info()
        print self.rw1.progs
        print "\n***** Printing Chained Commands ******\n"
        self.rw1.set_base_kwargs()
        self.rw1.chain_commands()


        # def test_run_chain_commands(self):
        #     self.rw1.parse_prog_info()
        #     self.rw1.test_paths()
        #     self.rw1.symlink_fastqs()
        #     self.rw1.chain_commands()
        #     luigi.build([TaskFlow(tasks=self.rw1.allTasks, task_name=self.rw1.bioproject)], local_scheduler=False,
        #                 workers=len(self.rw1.sample_fastq_work.keys()), lock_size=1)
        #     # # luigi.build([TaskFlow(tasks=self.rw1.allTasks)], local_scheduler=False, workers=2, lock_size=3)
        #     # luigi.build(self.rw1.allTasks, local_scheduler=False, workers=3, lock_size=3)


if __name__ == '__main__':
    unittest.main()
