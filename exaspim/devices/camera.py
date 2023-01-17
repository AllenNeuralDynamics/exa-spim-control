import numpy
from egrabber import *

# TODO: incorporate Memento datalogger.
#from exaspim.processes.data_logger import DataLogger


class Camera:

	def __init__(self, cfg):
		self.cfg = cfg  # TODO: we should not pass the whole config.
		self.gentl = EGenTL() # instantiate egentl
		self.grabber = EGrabber(self.gentl) # instantiate egrabber
		#self.data_logger_worker = None  # Memento img acquisition data logger.

	def configure(self):
		# realloc buffers appears to be allocating ram on the pc side, not camera side.
		self.grabber.realloc_buffers(self.cfg.egrabber_frame_buffer) # allocate RAM buffer N frames
		# Note: Msb unpacking is slightly faster according to camera vendor.
		self.grabber.stream.set("UnpackingMode", "Msb") # msb packing of 12-bit data
		# TODO: bit rate
		# grabber.RemotePort.set("PixelFormat", "Mono14");
		# Frame rate setting does not need to be set in external trigger mode.
		# TODO: round exposure time to one decimal place.
		self.grabber.remote.set("ExposureTime", self.cfg.camera_dwell_time*1.0e6) # set exposure time us, i.e. slit width
		# Note: Setting TriggerMode if it's already correct will throw an error
		if self.grabber.remote.get("TriggerMode") != "On": # set camera to external trigger mode
			self.grabber.remote.set("TriggerMode", "On") 
		self.grabber.remote.set("Gain", self.cfg.camera_digital_gain) # set digital gain to 1
		# TODO: we need to implement this somehow in the config
		#self.grabber.remote.set("OffsetX", "0")
		#self.grabber.remote.set("Width", "14192")

		# TODO: put the datalogger here.
		# data_logger is for the camera. It needs to exist between:
		#   cam.start() and cam.stop()
		# data_logger_worker = DataLogger(self.deriv_storage_dir,
		#                                 self.cfg.memento_path,
		#                                 f"{stack_prefix}_log")

	def start(self, frame_count: int = 0, live: bool = False):
		if live:
			self.grabber.start()
		else:
			# TODO: data logger needs to block until it is ready.
			# self.data_logger_worker.start()
			self.grabber.start(frame_count)

	def grab_frame(self):
		"""Retrieve a frame as a 2D numpy array with shape (rows, cols)."""
		# Note: creating the buffer and then "pushing" it at the end has the
		# 	effect of moving the internal camera frame buffer from the output
		# 	pool back to the input pool, so it can be reused.
		timeout_ms = int(30e3)
		with Buffer(self.grabber, timeout=timeout_ms) as buffer:
			ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR) # grab pointer to new frame
			data = ct.cast(ptr, ct.POINTER(ct.c_ubyte*self.cfg.sensor_column_count*self.cfg.sensor_row_count*2)).contents # grab frame data
			image = numpy.frombuffer(data, count=int(self.cfg.sensor_column_count*self.cfg.sensor_row_count), dtype=numpy.uint16).reshape((self.cfg.sensor_row_count,self.cfg.sensor_column_count)) # cast data to numpy array of correct size/datatype, push to numpy buffer
			self.tstamp = buffer.get_info(BUFFER_INFO_TIMESTAMP, INFO_DATATYPE_SIZET) # grab new frame time stamp
			return image

	def stop(self):
		self.grabber.stop()
		# self.data_logger_worker.stop()
		# self.data_logger_worker.close()

	def print_statistics(self, ch):

		num_frame = self.grabber.stream.get_info(STREAM_INFO_NUM_DELIVERED, INFO_DATATYPE_SIZET)
		num_queued = self.grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET) # number of available frames in ram buffer
		num_dropped = self.grabber.stream.get_info(STREAM_INFO_NUM_UNDERRUN, INFO_DATATYPE_SIZET) # number of underrun, i.e. dropped frames
		data_rate = self.grabber.stream.get('StatisticsDataRate') # stream data rate
		frame_rate = self.grabber.stream.get('StatisticsFrameRate') # stream frame rate

		print(('frame: {}, channel: ' + ch + ', size: {}x{}, time: {:.2f} ms, speed: {:.2f} MB/s, rate: {:.2f} fps, queue: {}/{}, dropped: {}').format(num_frame, self.cfg.cam_x, self.cfg.cam_y, (self.tstamp)/1000.0, data_rate, frame_rate, num_queued, self.cfg.ram_buffer, num_dropped))


