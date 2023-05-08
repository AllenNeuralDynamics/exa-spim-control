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
        self.grabber.remote.set("OffsetX", round((width_x/2 - self.cfg.sensor_column_count/2.0)/16)*16)  # center roi on sensor, multiple of 16
        self.grabber.remote.set("OffsetY", 0)  # set to 0 by default
        self.grabber.remote.set("Height", self.cfg.sensor_row_count) # set roi height
        self.grabber.remote.set("PixelFormat", "Mono14") # use 14-bit A/D
        # Frame rate setting does not need to be set in external trigger mode.
        # set exposure time us, i.e. slit width
        self.grabber.remote.set("ExposureTime", round(self.cfg.camera_dwell_time * 1.0e6, 1))
        # Note: Camera can potentially get stuck in a state that does not allow changing TriggerMode
        # starting and then stopping the camera resets this behavior
        self.start()
        self.stop()
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

    def start(self, frame_count: int = 1, live: bool = False):
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
        timeout_ms = int(1000e3)
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

    def collect_background(self, frame_average=1):
        """Retrieve a background image as a 2D numpy array with shape (rows, cols). """
        # Note: the background image is optionally averaged
        if self.grabber.remote.get("TriggerMode") != "Off":  # set camera to internal trigger mode
            self.grabber.remote.set("TriggerMode", "Off")
        # Initialize background image array
        bkg_image = numpy.zeros((frame_average, self.cfg.sensor_row_count, self.cfg.sensor_column_count), dtype='uint16')
        # Grab N background images
        self.start(frame_count=frame_average, live=False)
        for frame in range(0, frame_average):
            self.log.info(f"Capturing background image: {frame}")
            bkg_image[frame] = self.grab_frame()
        self.log.info(f"Averaging {frame_average} background images")
        self.stop()
        if self.grabber.remote.get("TriggerMode") != "On":  # set camera to external trigger mode
            self.grabber.remote.set("TriggerMode", "On")
        # Return median averaged 2D background image
        return numpy.median(bkg_image, axis = 0).astype('uint16')

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

    def get_mainboard_temperature(self):
        """get the mainboard temperature in degrees C."""
        self.grabber.remote.set("DeviceTemperatureSelector", "Mainboard")
        return self.grabber.remote.get("DeviceTemperature")

    def get_sensor_temperature(self):
        """get teh sensor temperature in degrees C."""
        self.grabber.remote.set("DeviceTemperatureSelector", "Sensor")
        sensor_temperature = self.grabber.remote.get("DeviceTemperature")
        # TODO: do we need to set the temp selector back, or can we skip this?
        self.grabber.remote.set("DeviceTemperatureSelector", "Mainboard")
        return sensor_temperature

    def schema_log_system_metadata(self):
        """Log camera metadata with the schema tag."""
        # log egrabber camera settings
        self.log.info('egrabber camera parameters', extra={'tags': ['schema']})
        categories = self.grabber.device.get(query.categories())
        for category in categories:
            features = self.grabber.device.get(query.features_of(category))
            for feature in features:
                if self.grabber.device.get(query.available(feature)):
                    if self.grabber.device.get(query.readable(feature)):
                        if not self.grabber.device.get(query.command(feature)):
                            self.log.info(f'device, {feature}, {self.grabber.device.get(feature)}',
                                          extra={'tags': ['schema']})

        categories = self.grabber.remote.get(query.categories())
        for category in categories:
            features = self.grabber.remote.get(query.features_of(category))
            for feature in features:
                if self.grabber.remote.get(query.available(feature)):
                    if self.grabber.remote.get(query.readable(feature)):
                        if not self.grabber.remote.get(query.command(feature)):
                            if feature != "BalanceRatioSelector" and feature != "BalanceWhiteAuto":
                                self.log.info(f'remote, {feature}, {self.grabber.remote.get(feature)}',
                                              extra={'tags': ['schema']})

        categories = self.grabber.stream.get(query.categories())
        for category in categories:
            features = self.grabber.stream.get(query.features_of(category))
            for feature in features:
                if self.grabber.stream.get(query.available(feature)):
                    if self.grabber.stream.get(query.readable(feature)):
                        if not self.grabber.stream.get(query.command(feature)):
                            self.log.info(f'stream, {feature}, {self.grabber.stream.get(feature)}',
                                          extra={'tags': ['schema']})

        categories = self.grabber.interface.get(query.categories())
        for category in categories:
            features = self.grabber.interface.get(query.features_of(category))
            for feature in features:
                if self.grabber.interface.get(query.available(feature)):
                    if self.grabber.interface.get(query.readable(feature)):
                        if not self.grabber.interface.get(query.command(feature)):
                            self.log.info(f'interface, {feature}, {self.grabber.interface.get(feature)}',
                                          extra={'tags': ['schema']})

        categories = self.grabber.system.get(query.categories())
        for category in categories:
            features = self.grabber.system.get(query.features_of(category))
            for feature in features:
                if self.grabber.system.get(query.available(feature)):
                    if self.grabber.system.get(query.readable(feature)):
                        if not self.grabber.system.get(query.command(feature)):
                            self.log.info(f'system, {feature}, {self.grabber.system.get(feature)}',
                                          extra={'tags': ['schema']})
