import threading
import numpy
from imaris_writer import PyImarisWriter as PW
from datetime import datetime

class MyCallbackClass(PW.CallbackClass):

	def __init__(self):

		self.mUserDataProgress=0

	def RecordProgress(self, progress, total_bytes_written):

		progress100=int(progress*100)
		if progress100 - self.mUserDataProgress >= 10:
			self.mUserDataProgress=progress100
			print('{}% Complete: {} GB written'.format(self.mUserDataProgress, total_bytes_written/1.0e9))

class DataWriter(object):

	def __init__(self):

		self.thread = None
		self.thread_list = []

	def configure(self, cfg):

		self.cfg = cfg
		self.filename = self.cfg.filename
		self.n_frames = self.cfg.n_frames
		self.datatype = self.cfg.datatype
		self.n_threads = self.cfg.n_threads
		self.cam_x = self.cfg.cam_x
		self.cam_y = self.cfg.cam_y
		self.sampling_x = self.cfg.sampling_x
		self.sampling_y = self.cfg.sampling_y
		self.sampling_z = self.cfg.sampling_z
		self.chunk_size = self.cfg.chunk_size

		if self.compression = 'lz4'
			self.compression = PW.eCompressionAlgorithmShuffleLZ4 # available compressors in pyimariswriter header
		elif self.compression = 'none'
			self.compression = PW.eCompressionAlgorithmNone # available compressors in pyimariswriter header

		image_size=PW.ImageSize(x=self.cam_x, y=self.cam_y, z=self.n_frames, c=1, t=1) # TODO add channels, hard coded as 1 now
		dimension_sequence=PW.DimensionSequence('x', 'y', 'z', 'c', 't')
		block_size=PW.ImageSize(x=self.cam_x, y=self.cam_y, z=self.chunk_size, c=1, t=1)
		sample_size=PW.ImageSize(x=1, y=1, z=1, c=1, t=1)

		options=PW.Options()
		options.mNumberOfThreads=self.n_threads
		options.mCompressionAlgorithmType=self.compression
		options.mEnableLogProgress=False

		application_name='PyImarisWriter'
		application_version='1.0.0'

		callback_class=MyCallbackClass()
		self.converter=(PW.ImageConverter(self.datatype, image_size, sample_size, dimension_sequence, block_size,
								self.filename + '.ims', options, application_name, application_version, callback_class))

	def write_block(self, data, chunk_num):
		self.thread = threading.Thread(target=self._write_block, args=(numpy.transpose(data,(2,1,0)), chunk_num,))
		self.thread.start() # start thread
		self.thread_list.append(self.thread) # append thread to list of threads

	def close(self):

		for thread in self.thread_list: # check for saving threads that are still running, join if still running
			if thread.is_alive():
				thread.join()

		# TODO this is hardcoded for a single channel
		adjust_color_range=False
		image_extents=PW.ImageExtents(0, 0, 0, self.cam_x*self.sampling_x, self.cam_y*self.sampling_y, self.n_frames*self.sampling_z)
		parameters=PW.Parameters()
		parameters.set_channel_name(0, 'CH0')
		time_infos=[datetime.today()]
		color_infos=[PW.ColorInfo() for _ in range(1)] # 1 -> TODO abstract this away => image_size.c
		color_infos[0].set_base_color(PW.Color(1, 1, 1, 1))
		color_infos[0].set_range(0,200)
		self.converter.Finish(image_extents, parameters, time_infos, color_infos, adjust_color_range)
		self.converter.Destroy()

	def _write_block(self, data, chunk_num):

		self.converter.CopyBlock(data, PW.ImageSize(x = 0, y = 0, z = chunk_num, c = 0, t = 0))