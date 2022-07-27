import subprocess
import os
import glob
import time

class DataLogger(object):

	def configure(self, cfg):

		self.cfg = cfg
		self.memento_path = self.cfg.memento_path
		self.filename = self.cfg.filename
		self.source_path = self.cfg.source_path
		self.destination_path = self.cfg.destination_path

	def start(self, file):

		self.cmd = subprocess.Popen(self.memento_path + " dump --output=" + self.source_path + "\\dump.memento --follow")
		time.sleep(1) # takes time for memento to boot sometimes

	def stop(self):

		subprocess.call(['taskkill', '/F', '/T', '/PID',  str(self.cmd.pid)]) # terminate memento subprocess
		self.cmd.wait()

	def close(self):

		fname = glob.glob(self.source_path + 'dum*.memento')
		os.rename(fname[0], self.source_path + self.filename + '.memento')