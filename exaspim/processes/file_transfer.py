import subprocess
import time


class FileTransfer:

	def configure(self, cfg):

		self.cfg = cfg

	def start(self, tile_name):

		self.cmd = subprocess.Popen(self.cfg.ftp + ' ' + self.cfg.source_path + tile_name + '* ' + self.cfg.destination_path + ' ' + self.cfg.ftp_flags)

	def stop(self, cmd):

		subprocess.call(['taskkill', '/F', '/T', '/PID',  str(cmd.pid)])

	def wait(self):

		while self.cmd.poll() is None:
			time.sleep(0.1)

	def close(self):

		self.cmd.kill()