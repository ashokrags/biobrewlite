from biobrewliteutils.wrappers import BaseWrapper as wr


import ftputil
ftp_host = ftputil.FTPHost("ftp.ensembl.org",user="anonymous")
ftp_host.getcwd()
ftp_host.path.isfile(ref_loc)
os.path.basename(ref_loc)
ftp_host.download(ref_loc,os.path.join(os.getcwd(),os.path.basename(ref_loc)))
ftp_host.download(gtf_loc,os.path.join(os.getcwd(),os.path.basename(gtf_loc)))