import unittest, os
from unittest import TestCase
from bioutils.access_sra.sra import SraUtils as SU
from bioutils.access_sra.sra import Sra_Element as SE


class TestSra(TestCase, SU):

    def setUp(self):
        print os.getcwd()
        self.infile = "./tests/test_fastqc.zip"
        self.parse_results_file()

    def test_fastqc_parser(self):
        self.parse_results_file()
        print " The file used is : " + str(self.infile) + "\n"
        print self.module_names

    def test_per_base_seq_qual_module(self):
        print " Capturing the sequence qualities"
        self.per_base_seq_quals = self.extract_seq_quals_module()


if __name__ == '__main__':
    unittest.main()
