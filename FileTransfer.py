import subprocess
import os
import glob

class FileTransfer(object):

	def __init__(self):

		# TODO add these params into config
		self.ftp = 'xcopy'
		self.ftp_flags = '/j /i'
		self.source_path = 'D:\\'
		self.destination_path = 'X:\\'


	def start(self, file):

		new_file = file
		while os.path.exists(self.destination_path + new_file):
			new_file = new_file + '_COPY'

		os.rename(self.source_path + file, self.source_path + new_file)

		cmd = subprocess.Popen(self.ftp + ' ' + self.source_path + new_file + ' ' + self.destination_path + ' ' + self.ftp_flags)

		return cmd

	def stop(self, cmd):

		subprocess.call(['taskkill', '/F', '/T', '/PID',  str(cmd.pid)]) # terminate memento subprocess

	def wait(self, cmd):

		cmd.wait()