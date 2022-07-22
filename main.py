#!/usr/bin/env python3
"""TEST SCRIPT FOR EXA-SPIM SYSTEM"""

import sys
import time
import os.path
import generate_waveforms as WaveformGenerator
import traceback
import numpy as np
import threading
import time
import subprocess
import glob
from egrabber import *
from tifffile import imwrite
from ni import WaveformGeneratorHardware
from imaris_writer import PyImarisWriter as PW
from multiprocessing.pool import ThreadPool
from datetime import datetime

class MyCallbackClass(PW.CallbackClass):

	def __init__(self):

		self.mUserDataProgress=0

	def RecordProgress(self, progress, total_bytes_written):

		progress100=int(progress*100)
		if progress100 - self.mUserDataProgress >= 10:
			self.mUserDataProgress=progress100
			print('{}% Complete: {} GB written'.format(self.mUserDataProgress, total_bytes_written/1.0e9))

def setup_daq(plot=False):
	# TODO add these params into config.
	n_frames = 20000
	dev_name = 'Dev1'
	rate = 1e4 # hz
	period = 210.0/1000 # ms
	ao_channels =   {'etl': 0,
					 'camera': 1,
					 'stage': 2,
					 'laser': 3
					}

	daq = WaveformGeneratorHardware(dev_name, rate, period, n_frames, ao_channels)
	t, voltages_t = WaveformGenerator.generate_waveforms()
	daq.configure()  # configure DAQ
	daq.assign_waveforms(voltages_t)
	if plot:
		print("Plotting waveforms to PDF.")
		WaveformGenerator.plot_waveforms_to_pdf(t, voltages_t)

	return daq

def setup_camera():
	# TODO add these params into config
	ram_buffer = 8 # frames
	frame_rate = 4.0 # frames/sec
	dwell_time = 5000.0 # us
	digital_gain = 1

	gentl = EGenTL() # instantiate egentl
	grabber = EGrabber(gentl) # instantiate egrabber
	grabber.realloc_buffers(ram_buffer) # allocate RAM buffer N frames
	grabber.stream.set("UnpackingMode", "Msb") # msb packing of 12-bit data
	grabber.remote.set("AcquisitionFrameRate", frame_rate) # set camera exposure fps
	grabber.remote.set("ExposureTime", dwell_time) # set exposure time us, i.e. slit width
	if grabber.remote.get("TriggerMode") != "On": # set camera to external trigger mode
		grabber.remote.set("TriggerMode", "On") 
	grabber.remote.set("Gain", digital_gain) # set digital gain to 1

	return grabber

def setup_imariswriter():
	# TODO add these params into config
	n_frames = 20000 # frames
	datatype = 'uint16'
	n_threads = 32 # threads
	compression = PW.eCompressionAlgorithmShuffleLZ4 # available compressors in pyimariswriter header
	cam_x = 14192 # px
	cam_y = 10640 # px
	chunk_size = 128 # frames
	output_filename = 'D:\\test.ims'

	image_size=PW.ImageSize(x=cam_x, y=cam_y, z=n_frames, c=1, t=1) # TODO add channels, hard coded as 1 now
	dimension_sequence=PW.DimensionSequence('x', 'y', 'z', 'c', 't')
	block_size=PW.ImageSize(x=cam_x, y=cam_y, z=chunk_size, c=1, t=1)
	sample_size=PW.ImageSize(x=1, y=1, z=1, c=1, t=1)
	num_voxels=image_size.x*image_size.y*image_size.z*image_size.c*image_size.t
	num_voxels_per_block=block_size.x*block_size.y*block_size.z*block_size.c*block_size.t

	options=PW.Options()
	options.mNumberOfThreads=n_threads
	options.mCompressionAlgorithmType=PW.eCompressionAlgorithmShuffleLZ4
	options.mEnableLogProgress=True

	application_name='PyImarisWriter'
	application_version='1.0.0'

	callback_class=MyCallbackClass()
	converter=(PW.ImageConverter(datatype, image_size, sample_size, dimension_sequence, block_size,
							output_filename, options, application_name, application_version, callback_class))

	return converter

def finish_imariswriter(converter):
	# TODO add these params into config
	n_frames = 20000 #  frames
	cam_x = 14192 # px
	cam_y = 10640 # px
	sampling_x = 0.75 # um/px
	sampling_y = 0.75 # um/px
	sampling_z = 0.75 # um/px

	# TODO this is hardcoded for a single channel
	adjust_color_range=False
	image_extents=PW.ImageExtents(0, 0, 0, cam_x*sampling_x, cam_y*sampling_y, n_frames*sampling_z)
	parameters=PW.Parameters()
	parameters.set_channel_name(0, 'CH0')
	time_infos=[datetime.today()]
	color_infos=[PW.ColorInfo() for _ in range(1)] # 1 -> TODO abstract this away => image_size.c
	color_infos[0].set_base_color(PW.Color(1, 1, 1, 1))
	color_infos[0].set_range(0,200)
	converter.Finish(image_extents, parameters, time_infos, color_infos, adjust_color_range)
	converter.Destroy()

def save_ims(converter, image, block_index):
	"""
	Save to IMS file
	:param values: image, block_index
		block index and image(s) to be saved
	:return None:
	"""
	converter.CopyBlock(image, block_index)

def max_project(image):
	"""
	Max project image
	:param values: image
		image array to max project
	:return max projected image
	"""
	return np.ndarray.max(image, axis=0)

def file_transfer(source_path, target_path):

	cmd = subprocess.Popen('xcopy ' + source_path + '_' + target_path + ' /J /Y')

	return cmd

def main():
	# TODO add these params into config
	n_frames = 20000 # frames
	datatype = 'uint16'
	n_threads = 32 # threads
	cam_x = 14192 # px
	cam_y = 10640 # px
	chunk_size = 128 # frames
	sampling_x = 0.75 # um/px
	sampling_y = 0.75 # um/px
	sampling_z = 0.75 # um/px

	grabber = setup_camera()
	daq = setup_daq()
	converter = setup_imariswriter()

	# initialize numpy array buffer
	images = np.zeros((chunk_size,cam_y,cam_x), dtype=datatype)  # initialize np array for image stack
	mip = np.zeros((cam_y,cam_x), dtype=datatype) # initialize np array for mip image

	# pre-initialize imaging loop variables
	frame_num = 0
	buffer_frame_num = 0
	thread_list = []
	block_index=PW.ImageSize() # initialize empty imaris block indices

	# initialize mip process pool
	pool = ThreadPool(processes=1)

	cmd = subprocess.Popen("C:\\Program Files\\Euresys\\Memento\\bin\\x86_64\\memento.exe dump --output=D:\\dump.memento --follow") # TODO abstract config of camera log file

	try:

		start_time = time.time()

		grabber.start(n_frames) # initialize grabber for n_frames
 
		while frame_num < n_frames:

			if frame_num == 0: # if first frame, start daq
				daq.start() # TODO. AO task runs continiously and is software triggered. consider tying this to a NI DO channel and hardware timing with a NI counter.

			with Buffer(grabber, timeout=2000) as buffer: # ask buffer for frame

				if frame_num == 0: # if first frame, grab t0 time stamp
					t0 = buffer.get_info(BUFFER_INFO_TIMESTAMP, INFO_DATATYPE_SIZET)

				ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR) # grab pointer to new frame
				tstamp = buffer.get_info(BUFFER_INFO_TIMESTAMP, INFO_DATATYPE_SIZET) # grab new frame time stamp
				data = ct.cast(ptr, ct.POINTER(ct.c_ubyte * cam_x*cam_y*2)).contents # grab frame data
				images[buffer_frame_num] = np.frombuffer(data, count=int(cam_x*cam_y), dtype=np.uint16).reshape((cam_y,cam_x)) # cast data to numpy array of correct size/datatype, push to numpy buffer
				frame_num += 1 # increment total frame count
				buffer_frame_num += 1 # increment index of numpy buffer

			# print acquisition statistics
			nq = grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET) # number of available frames in ram buffer
			nd = grabber.stream.get_info(STREAM_INFO_NUM_UNDERRUN, INFO_DATATYPE_SIZET) # number of underrun, i.e. dropped frames
			dr = grabber.stream.get('StatisticsDataRate') # stream data rate
			fr = grabber.stream.get('StatisticsFrameRate') # stream frame rate
			print('frame: {}, size: {}x{}, time: {:.2f} ms, speed: {:.2f} MB/s, rate: {:.2f} fps, queue: {}/{}, dropped: {}'.format(frame_num, cam_x, cam_y, (tstamp-t0)/1000.0, dr, fr, nq, 8, nd))

			# if index of buffer equals chunk_size write into imaris file
			if buffer_frame_num % chunk_size == 0:
				thread = threading.Thread(target=save_ims, args=(converter, np.transpose(images,(2,1,0)), block_index,)) # start ims saving thread. transpose numpy axes to match imarisfile axes
				thread.start() # start thread
				thread_list.append(thread) # append thread to list of threads
				if frame_num > chunk_size: # if this is not the first chunk, grab mip result from previous chunk
					mip = np.maximum(mip, async_result.get())
				async_result = pool.apply_async(max_project, (images,)) # kick off new mip calculation for current chunk
				buffer_frame_num = 0 # reset index of buffer
				block_index.z += 1 # increment block index in imaris file. only in z because block size x/y equals frame size i.e. no x/y blocks

			# if last frame and total frames is not a multiple of chunk size, finish up the last chunk
			elif frame_num == n_frames:
				thread=threading.Thread(target=save_ims, args=(converter, np.transpose(images,(2,1,0)), block_index,))
				thread.start()
				thread_list.append(thread)
				async_result = pool.apply_async(max_project, (images,))
				mip = np.maximum(mip, async_result.get())

			# TODO flush this out. prototype code for monitoring ram buffer status and pausing if danger of dropping frames
			# nq = grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET)
			# if nq < int(ram_buffer): # pause acquisition if ram buffer is more than half full
			#	 daq.stop() # stop ao task which stops acquisition
			#	 while nq != ram_buffer: # wait for ram buffer to empty
			#		 nq = grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET)
			#		 print('Available buffer: ' + str(nq) + '/' + str(ram_buffer))
			#		 time.sleep(0.1)
			#	 daq.start() # restart once buffer is flushed		

	finally:

		print((time.time() - start_time)/3600)

		daq.stop() # TODO issue here with CONTINUOUS timing. stops waveform at arbitrary spot. need to stop at the end of a DAQ cycle.
		daq.close() # close daq

		grabber.stop() # stop grabber

		for thread in thread_list: # check for saving threads that are still running, join if still running
			if thread.is_alive():
				thread.join()

		pool.close() # close mip process pool
		pool.join() # join if still running

		finish_imariswriter(converter) # close and finish imariswriter

		subprocess.call(['taskkill', '/F', '/T', '/PID',  str(cmd.pid)]) # terminate memento subprocess
		cmd.wait() # wait for process to terminate
		fname = glob.glob('D:\\dum*.memento')
		os.rename(fname[0], 'D:\\test.memento')

		imwrite('D:\\test_mip.tiff', mip) # TODO put this somewhere else. save mip tiff image

		start_time = time.time()

		cmd = file_transfer('D:\\test.memento', 'X:\\')
		cmd.wait()
		cmd = file_transfer('D:\\test_mip.tiff', 'X:\\')
		cmd.wait()
		cmd = file_transfer('D:\\test.ims', 'X:\\')
		cmd.wait()

		print((time.time() - start_time)/3600)

if __name__ == "__main__":

	main()
