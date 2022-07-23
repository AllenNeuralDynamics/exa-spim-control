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

		# TODO add these params into config
		self.n_frames = 500 # frames
		self.datatype = 'uint16'
		self.n_threads = 32 # threads
		self.compression = PW.eCompressionAlgorithmShuffleLZ4 # available compressors in pyimariswriter header
		self.cam_x = 14192 # px
		self.cam_y = 10640 # px
		self.sampling_x = 0.75 # um
		self.sampling_y = 0.75 # um
		self.sampling_z = 0.75 # um
		self.chunk_size = 128 # frames
		self.output_filename = 'D:\\test.ims'
		self.thread = None
		self.thread_list = []
		self.block_index = PW.ImageSize()

	def configure(self):

		image_size=PW.ImageSize(x=self.cam_x, y=self.cam_y, z=self.n_frames, c=1, t=1) # TODO add channels, hard coded as 1 now
		dimension_sequence=PW.DimensionSequence('x', 'y', 'z', 'c', 't')
		block_size=PW.ImageSize(x=self.cam_x, y=self.cam_y, z=self.chunk_size, c=1, t=1)
		sample_size=PW.ImageSize(x=1, y=1, z=1, c=1, t=1)

		options=PW.Options()
		options.mNumberOfThreads=self.n_threads
		options.mCompressionAlgorithmType=self.compression
		options.mEnableLogProgress=True

		application_name='PyImarisWriter'
		application_version='1.0.0'

		callback_class=MyCallbackClass()
		self.converter=(PW.ImageConverter(self.datatype, image_size, sample_size, dimension_sequence, block_size,
								self.output_filename, options, application_name, application_version, callback_class))

	def write_block(self, data):

		self.thread = threading.Thread(target=self._write_block, args=(numpy.transpose(data,(2,1,0)),))
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

	def _write_block(self, data):

		self.converter.CopyBlock(data, self.block_index)
		self.block_index.z += 1