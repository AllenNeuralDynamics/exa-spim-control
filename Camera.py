import numpy
from egrabber import *

class Camera(object):

	def __init__(self):

		self.gentl = EGenTL() # instantiate egentl
		self.grabber = EGrabber(self.gentl) # instantiate egrabber

	def configure(self, cfg):

		self.cfg = cfg
		self.n_frames = self.cfg.n_frames
		self.cam_x = self.cfg.cam_x
		self.cam_y = self.cfg.cam_y
		self.ram_buffer = self.cfg.ram_buffer
		self.frame_rate = self.cfg.frame_rate
		self.dwell_time = self.cfg.dwell_time
		self.digital_gain = self.cfg.digital_gain

		self.grabber.realloc_buffers(self.ram_buffer) # allocate RAM buffer N frames
		self.grabber.stream.set("UnpackingMode", "Msb") # msb packing of 12-bit data
		self.grabber.remote.set("AcquisitionFrameRate", self.frame_rate) # set camera exposure fps
		self.grabber.remote.set("ExposureTime", self.dwell_time*1000) # set exposure time us, i.e. slit width
		if self.grabber.remote.get("TriggerMode") != "On": # set camera to external trigger mode
			self.grabber.remote.set("TriggerMode", "On") 
		self.grabber.remote.set("Gain", self.digital_gain) # set digital gain to 1

	def start(self, live = False):

		if live == False:
			self.grabber.start(self.n_frames)
		else:
			self.grabber.start()

	def grab_frame(self):

		buffer = Buffer(self.grabber, timeout = int(2*self.dwell_time*1000))
		ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR) # grab pointer to new frame
		data = ct.cast(ptr, ct.POINTER(ct.c_ubyte*self.cam_x*self.cam_y*2)).contents # grab frame data
		image = numpy.frombuffer(data, count=int(self.cam_x*self.cam_y), dtype=numpy.uint16).reshape((self.cam_y,self.cam_x)) # cast data to numpy array of correct size/datatype, push to numpy buffer
		self.tstamp = buffer.get_info(BUFFER_INFO_TIMESTAMP, INFO_DATATYPE_SIZET) # grab new frame time stamp
		buffer.push()

		return image		

	def stop(self):

		self.grabber.stop()

	def print_statistics(self):

		num_frame = self.grabber.stream.get_info(STREAM_INFO_NUM_DELIVERED, INFO_DATATYPE_SIZET)
		num_queued = self.grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET) # number of available frames in ram buffer
		num_dropped = self.grabber.stream.get_info(STREAM_INFO_NUM_UNDERRUN, INFO_DATATYPE_SIZET) # number of underrun, i.e. dropped frames
		data_rate = self.grabber.stream.get('StatisticsDataRate') # stream data rate
		frame_rate = self.grabber.stream.get('StatisticsFrameRate') # stream frame rate

		print('frame: {}, size: {}x{}, time: {:.2f} ms, speed: {:.2f} MB/s, rate: {:.2f} fps, queue: {}/{}, dropped: {}'.format(num_frame, self.cam_x, self.cam_y, (self.tstamp)/1000.0, data_rate, frame_rate, num_queued, self.ram_buffer, num_dropped))


