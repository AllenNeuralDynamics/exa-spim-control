import subprocess
import os
import glob
import time

class DataLogger(object):

	def __init__(self):

		# TODO add these params into config
		self.memento_path = "C:\\Program Files\\Euresys\\Memento\\bin\\x86_64\\memento.exe"
		self.source_path = 'D:\\'
		self.destination_path = 'X:\\'

	def start(self, file):
		self.file = file
		self.cmd = subprocess.Popen(self.memento_path + " dump --output=" + self.source_path + "\\dump.memento --follow")
		time.sleep(1) # takes time for memento to boot sometimes

	def stop(self):

		subprocess.call(['taskkill', '/F', '/T', '/PID',  str(self.cmd.pid)]) # terminate memento subprocess
		self.cmd.wait()

	def close(self):

		fname = glob.glob(self.source_path + 'dum*.memento')
		os.rename(fname[0], self.source_path + self.file)