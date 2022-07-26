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

	def start(self, files):

		self.cmd_list = []

		for file in files:

			new_file = file
			duplicate = 0
			while os.path.exists(self.destination_path + new_file):
				duplicate += 1
				new_file = file + '.' + str(duplicate)

			os.rename(self.source_path + file, self.source_path + new_file)

			cmd = subprocess.Popen(self.ftp + ' ' + self.source_path + new_file + ' ' + self.destination_path + ' ' + self.ftp_flags)
			self.cmd_list.append(cmd)

	def stop(self, cmd):

		subprocess.call(['taskkill', '/F', '/T', '/PID',  str(cmd.pid)]) # terminate memento subprocess

	def wait(self):

		for cmd in self.cmd_list:
			cmd.wait()

	def close(self):

		for cmd in self.cmd_list:
			cmd.kill()
		self.cmd_list = []