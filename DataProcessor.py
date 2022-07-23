import nidaqmx
import time
import numpy
from multiprocessing.pool import ThreadPool

class DataProcessor(object):

	def __init__(self):

		# TODO add these params into config
		self.processes = 1

	def configure(self):
		self.pool = ThreadPool(processes=self.processes)

	def max_project(self, image):

		self.async_result = self.pool.apply_async(self._max_project, (image,))

	def update_max_project(self, mip):

		return numpy.maximum(mip, self.async_result.get())

	def close(self):
		
		self.pool.close()
		self.pool.join()

	def _max_project(self, image):
		"""
		Max project image
		:param values: image
			image array to max project
		:return max projected image
		"""
		return numpy.ndarray.max(image, axis=0)