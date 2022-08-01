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

	def configure(self, cfg, tile_name):

		self.cfg = cfg
		self.source_path = self.cfg.source_path
		self.filename = self.cfg.filename
		self.n_frames = self.cfg.n_frames
		self.datatype = self.cfg.datatype
		self.n_threads = self.cfg.n_threads
		self.cam_x = self.cfg.cam_x
		self.cam_y = self.cfg.cam_y
		self.pixel_x = self.cfg.pixel_x
		self.pixel_y = self.cfg.pixel_y
		self.pixel_z = self.cfg.pixel_z
		self.x_overlap = self.cfg.x_overlap
		self.y_overlap = self.cfg.y_overlap
		self.chunk_size = self.cfg.chunk_size
		self.n_channels = self.cfg.n_channels
		self.tile_name = tile_name

		image_size=PW.ImageSize(x=self.cam_x, y=self.cam_y, z=self.n_frames, c=1, t=1) # TODO add channels, hard coded as 1 now
		dimension_sequence=PW.DimensionSequence('x', 'y', 'z', 'c', 't')
		block_size=PW.ImageSize(x=self.cam_x, y=self.cam_y, z=self.chunk_size, c=1, t=1)
		sample_size=PW.ImageSize(x=1, y=1, z=1, c=1, t=1)

		options=PW.Options()
		options.mNumberOfThreads=self.n_threads
		if self.cfg.compression == 'lz4':
			options.mCompressionAlgorithmType = PW.eCompressionAlgorithmShuffleLZ4 # available compressors in pyimariswriter header
		elif self.cfg.compression == 'none':
			options.mCompressionAlgorithmType =  PW.eCompressionAlgorithmNone # available compressors in pyimariswriter header
		options.mEnableLogProgress=True

		application_name='PyImarisWriter'
		application_version='1.0.0'

		callback_class=MyCallbackClass()
		self.converter=(PW.ImageConverter(self.datatype, image_size, sample_size, dimension_sequence, block_size,
								self.source_path + self.tile_name + '.ims', options, application_name, application_version, callback_class))

	def write_block(self, data, chunk_num):
		self.thread = threading.Thread(target=self._write_block, args=(numpy.transpose(data,(2,1,0)), chunk_num))
		self.thread.start() # start thread
		self.thread_list.append(self.thread) # append thread to list of threads

	def close(self, x_tile, y_tile):

		for thread in self.thread_list: # check for saving threads that are still running, join if still running
			if thread.is_alive():
				thread.join()

		# TODO this is hardcoded for a single channel
		adjust_color_range=False
		x0 = self.cam_x*self.pixel_x*(x_tile)*(1-self.x_overlap/100) 
		y0 = self.cam_y*self.pixel_y*(y_tile)*(1-self.y_overlap/100) 
		z0 = 0
		xf = x0 + self.cam_x*self.pixel_x
		yf = y0 + self.cam_y*self.pixel_y
		zf = z0 + self.n_frames*self.pixel_z
		image_extents=PW.ImageExtents(x0, y0, z0, xf, yf, zf)
		parameters=PW.Parameters()
		# parameters.set_channel_name(0, 'CH0')
		time_infos=[datetime.today()]
		color_infos=[PW.ColorInfo() for _ in range(1)] # 1 -> TODO abstract this away => image_size.c
		color_infos[0].set_base_color(PW.Color(1, 1, 1, 1))
		# color_infos[0].set_range(0,200)
		self.converter.Finish(image_extents, parameters, time_infos, color_infos, adjust_color_range)
		self.converter.Destroy()

	def _write_block(self, data, chunk_num):

		self.converter.CopyBlock(data, PW.ImageSize(x = 0, y = 0, z = chunk_num, c = 0, t = 0))