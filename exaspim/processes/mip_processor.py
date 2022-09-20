import numpy as np
from multiprocessing.pool import ThreadPool


class MIPProcessor:

	def __init__(self):
		self.pool = ThreadPool(processes=1)
		self.async_result = None

	def max_project(self, image):
		self.async_result = self.pool.apply_async(self._max_project, (image,))

	def update_max_project(self, mip):
		return np.maximum(mip, self.async_result.get())

	def close(self):
		self.pool.close()
		self.pool.join()

	def _max_project(self, image):
		# FIXME: this axis might change depending on frame format.
		return np.ndarray.max(image, axis=0)