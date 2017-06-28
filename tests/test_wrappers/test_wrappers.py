import biobrewliteutils.wrappers as wr
import unittest, os, saga
from definedworkflows.rnaseq.rnaseqworkflow import BaseWorkflow as bwflw
from definedworkflows.rnaseq.rnaseqworkflow import RnaSeqFlow as rsw


#
# class TestWrapper(unittest.TestCase):
#
#     def setUp(self):
#         self.wrapper_name = "fastqc"
#         self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run.yaml"
#         self.rw1 = bwflw(self.parmsfile)
#         self.test_wrap = wr.BaseWrapper(self.wrapper_name,cwd=self.rw1.run_parms['work_dir'],
#                                         stdout=os.path.join(self.rw1.run_parms['work_dir'],'fastqc.log'))
#
#     def test_wrapper(self):
#         print "\n***** Testing  the Base wrapper class *****\n"
#         for k, v in self.test_wrap.__dict__.iteritems():
#             print k + ": " + str(v) +  "\n"
#         #print "**** Using inspect ***\n"
#         # for x in inspect.getmembers(self.test_wrap):
#         #     print x[0], x[1], "\n"n
#         #test_wrap.run('fastqc')
#
#     def test_check_version(self):
#         self.test_wrap.version()
#
#     def test_run(self):
#         self.test_wrap.setup_run()
#         self.assertEqual(self.test_wrap.cmd[0],"fastqc")
#
class TestFastqc(unittest.TestCase):

    def setUp(self):
        self.wrapper_name = "fastqc"
        self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run.yaml"
        self.rw1 = rsw(self.parmsfile)
        self.rw1.set_base_kwargs()
        self.rw1.parse_prog_info()
        self.wrapper_name = 'fastqc'
        self.fastqc_test = wr.FastQC(self.wrapper_name, "test_samp",
                                     stdout=os.path.join(self.rw1.run_parms['work_dir'], 'fastqc.log'),
                                     **dict(self.rw1.base_kwargs))


    def test_fastqc_wrapper(self):
        print "\n***** Testing Fastqc_wrapper command *****\n"
        print self.fastqc_test.run_command

        # print "\n***** Testing Fastqc_wrapper *****\n"
        # for k, v in self.fastqc_test.__dict__.iteritems():
        #     print k + ": " + str(v) +  "\n"

class TestGsnap(unittest.TestCase):

    def setUp(self):
        self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run.yaml"
        self.rw1 = rsw(self.parmsfile)
        self.rw1.set_base_kwargs()
        self.rw1.parse_prog_info()
        self.wrapper_name = 'gsnap'
        self.add_args = self.rw1.progs[self.wrapper_name]
        #use  *self.add_args to unroll the list
        new_base_kwargs = self.rw1.update_job_parms(self.wrapper_name)
        self.gsnap_test = wr.Gsnap(self.wrapper_name, "test_samp", *self.add_args,
                                   stdout=os.path.join(self.rw1.align_dir, 'gsnap.sam'),
                                   **dict(new_base_kwargs))


    def test_gsnap_wrapper(self):
        print "\n***** Testing Gsnap_wrapper command *****\n"
        print self.gsnap_test.run_command
        #
        # print "\n***** Testing Gsnap_wrapper *****\n"
        # for k, v in self.gsnap_test.__dict__.iteritems():
        #     print k + ": " + str(v) +  "\n"

class TestSamMarkDup(unittest.TestCase):

    def setUp(self):
        self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run.yaml"
        self.rw1 = rsw(self.parmsfile)
        self.rw1.set_base_kwargs()
        self.rw1.parse_prog_info()
        self.wrapper_name = 'bammarkduplicates2'
        self.biobambammarkdup_test=wr.BiobambamMarkDup(self.wrapper_name,"test_samp",
                                                       stdout=os.path.join(self.rw1.log_dir, 'bammarkduplicates.log'),
                                                       **dict(self.rw1.base_kwargs))


    def test_sammarkduo_wrapper(self):
        print "\n***** Testing biobambam_wrapper command *****\n"
        print self.biobambammarkdup_test.run_command

        # print "\n***** Testing biobambam_wrapper *****\n"
        # for k, v in self.biobambammarkdup_test.__dict__.iteritems():
        #     print k + ": " + str(v) +  "\n"


class TestQualimap(unittest.TestCase):
    def setUp(self):
        self.parmsfile = "/Users/aragaven/PycharmProjects/biobrewlite/tests/test_rnaseq_workflow/test_run.yaml"
        self.rw1 = rsw(self.parmsfile)
        # self.rw1.parse_prog_info()
        self.wrapper_name = 'qualimap_rnaseq'
        self.qualimap_test = wr.QualiMapRnaSeq(self.wrapper_name, "test_samp",
                                               stdout=os.path.join(self.rw1.log_dir, 'qualimap.log'),
                                               **dict(self.rw1.base_kwargs))

    def test_qualimap_wrapper(self):
        print "\n***** Testing Qualimap_wrapper command *****\n"
        print self.qualimap_test.run_command

        # print "\n***** Testing Qualimap_wrapper *****\n"
        # for k, v in self.qualimap_test.__dict__.iteritems():
        #     print k + ": " + str(v) +  "\n"


if __name__ == '__main__':
    unittest.main()
