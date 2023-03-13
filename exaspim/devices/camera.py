import numpy
from egrabber import *
import logging


# TODO: incorporate Memento datalogger.
# from exaspim.processes.data_logger import DataLogger


class Camera:

    def __init__(self, cfg):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.cfg = cfg  # TODO: we should not pass the whole config.
        self.gentl = EGenTL()  # instantiate egentl
        self.grabber = EGrabber(self.gentl)  # instantiate egrabber

    # self.data_logger_worker = None  # Memento img acquisition data logger.

    def configure(self):
        # realloc buffers appears to be allocating ram on the pc side, not camera side.
        self.grabber.realloc_buffers(self.cfg.egrabber_frame_buffer)  # allocate RAM buffer N frames
        # Note: Msb unpacking is slightly faster according to camera vendor.
        self.grabber.stream.set("UnpackingMode", "Msb")  # msb packing of 12-bit data
        self.grabber.remote.set("OffsetX", 0) # set to 0 by default
        self.grabber.remote.set("Width", int(self.cfg.sensor_column_count)) # set roi width
        # TODO: OffsetX gets rounded to a multiple of 16.
        #   Log (warning level) if the desired OffsetX differs from the actual.
        width_x = self.grabber.remote.get("SensorWidth")
        self.grabber.remote.set("OffsetX", round(width_x/2 - self.cfg.sensor_column_count / 2.0))  # center roi on sensor
        self.grabber.remote.set("OffsetY", 0)  # set to 0 by default
        self.grabber.remote.set("Height", self.cfg.sensor_row_count) # set roi height
        self.grabber.RemotePort.set("PixelFormat", "Mono14") # use 14-bit A/D
        # Frame rate setting does not need to be set in external trigger mode.
        # set exposure time us, i.e. slit width
        self.grabber.remote.set("ExposureTime", round(self.cfg.camera_dwell_time * 1.0e6, 1))
        # Note: Setting TriggerMode if it's already correct will throw an error
        if self.grabber.remote.get("TriggerMode") != "On":  # set camera to external trigger mode
            self.grabber.remote.set("TriggerMode", "On")
        self.grabber.remote.set("Gain", self.cfg.camera_digital_gain)  # set digital gain to 1

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
            ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR)  # grab pointer to new frame
            # grab frame data
            data = ct.cast(ptr, ct.POINTER(ct.c_ubyte * self.cfg.sensor_column_count * self.cfg.sensor_row_count * 2)).contents
            # cast data to numpy array of correct size/datatype:
            image = numpy.frombuffer(data, count=int(self.cfg.sensor_column_count * self.cfg.sensor_row_count),
                                     dtype=numpy.uint16).reshape((self.cfg.sensor_row_count,
                                                                  self.cfg.sensor_column_count))
            #self.tstamp = buffer.get_info(BUFFER_INFO_TIMESTAMP, INFO_DATATYPE_SIZET)  # grab new frame time stamp
            return image

    def stop(self):
        self.grabber.stop()
        # self.data_logger_worker.stop()
        # self.data_logger_worker.close()

    def get_camera_acquisition_state(self):
        """return a dict with the state of the acquisition buffers"""
        # Detailed description of constants here:
        # https://documentation.euresys.com/Products/Coaxlink/Coaxlink/en-us/Content/IOdoc/egrabber-reference/namespace_gen_t_l.html#a6b498d9a4c08dea2c44566722699706e
        state = {}
        state['frame_index'] = self.grabber.stream.get_info(STREAM_INFO_NUM_DELIVERED, INFO_DATATYPE_SIZET)
        state['in_buffer_size'] = self.grabber.stream.get_info(STREAM_INFO_NUM_QUEUED,
                                                               INFO_DATATYPE_SIZET)
        state['out_buffer_size'] = self.grabber.stream.get_info(STREAM_INFO_NUM_AWAIT_DELIVERY,
                                                                INFO_DATATYPE_SIZET)
        state['dropped_frames'] = self.grabber.stream.get_info(STREAM_INFO_NUM_UNDERRUN,
                                                               INFO_DATATYPE_SIZET)  # number of underrun, i.e. dropped frames
        state['data_rate'] = self.grabber.stream.get('StatisticsDataRate')  # stream data rate
        state['frame_rate'] = self.grabber.stream.get('StatisticsFrameRate')  # stream frame rate
        self.log.debug(f"frame: {state['frame_index']}, "
                       f"input buffer size: {state['in_buffer_size']}, "
                       f"output buffer size: {state['out_buffer_size']}, "
                       f"dropped_frames: {state['dropped_frames']}, "
                       f"data rate: {state['data_rate']:.2f} [MB/s], "
                       f"frame rate: {state['frame_rate']:.2f} [fps].")
        return state
