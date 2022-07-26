import sys
import time
import os.path
import traceback
import time
import glob
import Camera
import WaveformGenerator
import DataWriter
import DataProcessor
import FileTransfer
import DataLogger
import numpy
from tifffile import imwrite

def main():

	# TODO add these params into config
	n_tiles = 1
	n_frames = 4000 # frames
	datatype = 'uint16'
	cam_x = 14192 # px
	cam_y = 10640 # px
	chunk_size = 128 # frames

	camera = Camera.Camera()
	waveform_generator = WaveformGenerator.WaveformGenerator()
	data_writer = DataWriter.DataWriter()
	data_processor = DataProcessor.DataProcessor()
	file_transfer = FileTransfer.FileTransfer()
	data_logger = DataLogger.DataLogger()

	for tile in range(0, n_tiles):

		images = numpy.zeros((chunk_size,cam_y,cam_x), dtype=datatype)
		mip = numpy.zeros((cam_y,cam_x), dtype=datatype)

		frame_num = 0
		buffer_frame_num = 0
		chunk_num = 0

		camera.configure()
		waveform_generator.configure()
		waveform_generator.generate_waveforms()
		data_writer.configure('D:\\' + 'tile_' + str(tile) + '.ims')
		data_processor.configure()
		data_logger.start('tile_' + str(tile) + '.memento')

		try:

			start_time = time.time()

			camera.start()

			while frame_num < n_frames:

				if frame_num == 0:
					waveform_generator.start()

				images[buffer_frame_num] = camera.grab_frame()
				frame_num += 1
				buffer_frame_num += 1

				camera.print_statistics()

				if buffer_frame_num % chunk_size == 0:
					data_writer.write_block(images, chunk_num)
					if frame_num > chunk_size:
						mip = data_processor.update_max_project(mip)
					data_processor.max_project(images)
					buffer_frame_num = 0
					chunk_num += 1

				elif frame_num == n_frames:
					data_writer.write_block(images, chunk_num)
					data_processor.max_project(images)
					mip = data_processor.update_max_project(mip)

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

			waveform_generator.stop()
			camera.stop()
			data_logger.stop()

			waveform_generator.close()
			data_writer.close()
			data_processor.close()
			data_logger.close()

			print('imaging time: ' + str((time.time()-start_time)/3600))

			imwrite('D:\\tile_' + str(tile) + '_mip.tiff', mip) # TODO put this somewhere else. save mip tiff image

			start_time = time.time()

			if tile > 0:
				wait_start = time.time()
				file_transfer.wait()
				file_transfer.close()
				os.remove('D:\\' + 'tile_' + str(tile-1) + '.ims')
				os.remove('D:\\' + 'tile_' + str(tile-1) + '.memento')
				os.remove('D:\\' + 'tile_' + str(tile-1) + '_mip.tiff')
				print('wait time: ' + str((time.time() - wait_start)/3600))

			file_transfer.start(['tile_' + str(tile) + '.memento', 'tile_' + str(tile) + '_mip.tiff', 'tile_' + str(tile) + '.ims'])

			if tile == n_tiles-1:
				wait_start = time.time()
				file_transfer.wait()
				file_transfer.close()
				os.remove('D:\\' + 'tile_' + str(tile) + '.ims')
				os.remove('D:\\' + 'tile_' + str(tile) + '.memento')
				os.remove('D:\\' + 'tile_' + str(tile) + '_mip.tiff')
				print('wait time: ' + str((time.time() - wait_start)/3600))

if __name__ == "__main__":

	main()
