import nidaqmx
import time
import numpy
from multiprocessing.pool import ThreadPool

class DataProcessor(object):

	def configure(self, cfg):

		self.cfg = cfg
		self.pool = ThreadPool(processes=1)

	def max_project(self, image):

		self.async_result = self.pool.apply_async(self._max_project, (image,))

	def update_max_project(self, mip):

		return numpy.maximum(mip, self.async_result.get())

	def close(self):
		
		self.pool.close()
		self.pool.join()

	def _max_project(self, image):

		return numpy.ndarray.max(image, axis=0)