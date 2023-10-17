import numpy
from egrabber import *
import logging

class Camera:

    def __init__(self, cfg):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.cfg = cfg  # TODO: we should not pass the whole config.
        self.gentl = EGenTL()  # instantiate egentl
        self.grabber = EGrabber(self.gentl)  # instantiate egrabber

        # attributes
        self.attributes.min_exposure_time_ms = self.grabber.remote.get()
        self.attributes.max_exposure_time_ms = self.grabber.remote.get()
        self.attributes.min_line_interval_us = self.grabber.remote.get()
        self.attributes.max_line_interval_us = self.grabber.remote.get()
        self.attributes.min_height_px = self.grabber.remote.get()
        self.attributes.min_width_px = self.grabber.remote.get()
        self.attributes.max_height_px = self.grabber.remote.get("SensorHeight")
        self.attributes.max_width_px = self.grabber.remote.get("SensorWidth")
        # Note: ROI = [X0, X1, Y0, Y1] corner coordinates
        self.roi = [self.grabber.remote.get(), 
                    self.grabber.remote.get(),
                    self.grabber.remote.get(),
                    self.grabber.remote.get()]
        self.attributes.pixel_size_um = self.cfg.pixel_size_um # <- comes from confi
        self.attributes.pixel_type_bits = self.grabber.remote.get()
        self.attributes.bit_packing_mode = self.grabber.remote.get()
        self.attributes.binning = self.grabber.remote.get()
        # Note: trigger mode, source, polarity
        self.attributes.trigger = [self.grabber.remote.get(),
                                   self.grabber.remote.get(),
                                   self.grabber.remote.get()]
        # Note: this cannot be set for the VP-151MX camera
        self.attributes.readout_mode = "rolling"
        # Note: this cannot be set for the VP-151MX camera
        self.attributes.readout_direction = "forward"

    class ReadoutMode(Enum):
        ROLLING = "rolling"

    class ReadoutDirection(Enum):
        FORWARD = "forward"

    class TriggerMode(Enum):
        ON = "on"
        OFF = "off"

    class TriggerSource(Enum):
        INTERNAL = "internal"
        EXTERNAL = "external"

    class TriggerPolarity(Enum):
        POSITIVE = "postive"
        NEGATIVE = "negative"

    class PixelType(Enum):
        P8 = "Mono8"
        P10 = "Mono10"
        P12 = "Mono12"
        P14 = "Mono14"
        P16 = "Mono16"

    class Binning(Enum):
        X1 = "1"
        X2 = "2"
        X4 = "4"

    def get_exposure_time_ms(self):
        return self.grabber.remote.get()

    def set_exposure_time_ms(self, exposure_time_ms: float = 10):
        # Note: round ms to nearest us
        self.grabber.remote.set("ExposureTime", round(exposure_time_ms * 1.0e6, 1))
        self.log.info(f"Exposure time set to: {exposure_time_ms} ms")
        self.attributes.exposure_time_ms = exposure_time_ms

    def set_roi(self, height_px: int, width_px: int):
        self.grabber.remote.set("OffsetX", 0)
        self.grabber.remote.set("Width", int(width_px))
        actual_width_px = self.grabber.remote.get("Width")
        # Note: center roi on sensor, must be multiple of 16
        centered_offset_x_px = round((actual_width_px/2 - width_px/2.0)/16)*16
        self.grabber.remote.set("OffsetX", centered_offset_x_px)
        
        self.grabber.remote.set("OffsetY", 0)
        self.grabber.remote.set("Height", height_px)
        actual_height_px = self.grabber.remote.get("Height")
        # Note: center roi on sensor, must be multiple of 16
        centered_offset_y_px = round((actual_width_px/2 - width_px/2.0)/16)*16
        self.grabber.remote.set("OffsetY", centered_offset_y_px)

        if actual_width_px != width_px:
            self.log.warning(f"ROI width set to {actual_width_px} px not {width_px} px!")
        if actual_height_px != height_px:
            self.log.warning(f"ROI height set to {actual_height_px} px not {height_px} px!")

        self.log.info(f"ROI set to: {actual_width_px} x {actual_height_px} [WxH]")
        self.log.info(f"ROI offset set to: {centered_offset_x_px} x {centered_offset_y_px} [WxH]")

        self.attributes.roi = [centered_offset_x_px,
                               centered_offset_x_px + actual_width_px,
                               centered_offset_y_px,
                               centered_offset_y_px + actual_height_px]

    def get_roi(self):
        return [self.grabber.remote.get("OffsetX"),
                self.grabber.remote.get("OffsetX") + self.grabber.remote.get("Width"),
                self.grabber.remote.get("OffsetY"),
                self.grabber.remote.get("OffsetY") + self.grabber.remote.get("Height")]

    def set_pixel_type(self, pixel_type_bits: PixelType):
        # Note: for the Vieworks VP-151MX camera, the pixel type also controls line interval
        self.grabber.remote.set("PixelFormat", pixel_type_bits)
        if pixel_type_bits == PixelType.P8:
            self.attributes.line_interval_us = 15.00
        elif pixel_type_bits == PixelType.P10:
            self.attributes.line_interval_us = 15.00
        elif pixel_type_bits == PixelType.P12:
            self.attributes.line_interval_us = 15.00
        elif pixel_type_bits == PixelType.P14:
            self.attributes.line_interval_us = 20.21
        elif pixel_type_bits == PixelType.P16:
            self.attributes.line_interval_us = 45.44
        else:
            self.log.error("Not a valid pixel type")
            raise
        self.log.info(f"pixel_type_set_to: {pixel_type_bits} bits")
        self.attributes.pixel_type_bits = pixel_type_bits

    def get_pixel_type(self):
        return self.grabber.remote.set("PixelFormat")

    def set_line_interval_us(self, line_interval_us):
        self.log.warning(f"Line interval is controlled by pixel type for the VP-151MX camera!")
        pass

    def get_line_interval_us(self):
        self.log.warning(f"Line interval is controlled by pixel type for the VP-151MX camera!")
        return self.attributes.line_interval_us

    def set_readout_mode(self, readout_mode: ReadoutMode):
        self.log.warning(f"Readout mode cannot be set for the VP-151MX camera!")

    def get_readout_mode(self):
        self.log.warning(f"Readout mode cannot be set for the VP-151MX camera!")
        return self.attributes.readout_mode

    def set_readout_direction(self, readout_direction: ReadoutDirection):
        self.log.warning(f"Readout direction cannot be set for the VP-151MX camera!")

    def get_readout_direction(self):
        self.log.warning(f"Readout direction cannot be set for the VP-151MX camera!")
        return self.attributes.readout_direction

    def set_trigger(self, mode: TriggerMode, source: TriggerSource, polarity: TriggerPolarity):
        # Note: Setting TriggerMode if it's already correct will throw an error
        if self.grabber.remote.get("TriggerMode") != "On":  # set camera to external trigger mode
            self.grabber.remote.set("TriggerMode", "On")
        self.grabber.remote.set("TriggerSource")...
        self.grabber.remote.set("TriggerPolarity")...

        self.attributes.trigger_mode = mode
        self.attributes.trigger_source = source
        self.attributes.trigger_polarity = polarity

        self.log.info(f"Trigger set to mode: {mode}, source: {source}, polarity: {polarity}")

    def get_trigger(self):
        return [self.grabber.remote.get(),
                self.grabber.remote.get(),
                self.grabber.remote.get()]

    def set_binning(self, binning: Binning): 
        self.grabber.remote.set("Binning")...
        self.attributes.binning = binning
        self.log.info(f"binning set to: {binning}")

    def get_binning(self): 
        return self.grabber.remote.get("Binning")...

    def get_mainboard_temperature_c(self):
        """get the mainboard temperature in degrees C."""
        mainboard_temperature_c = self.grabber.remote.set("DeviceTemperatureSelector", "Mainboard")
        self.attributes.mainboard_temperature_c = mainboard_temperature_c
        return mainboard_temperature_c

    def get_sensor_temperature_c(self):
        """get teh sensor temperature in degrees C."""
        sensor_temperature_c = self.grabber.remote.set("DeviceTemperatureSelector", "Sensor")
        self.attributes.sensor_temperature_c = sensor_temperature_c
        return sensor_temperature_c

    def arm(self, frame_count: int = 1):
        # realloc buffers appears to be allocating ram on the pc side, not camera side.
        self.grabber.realloc_buffers(self.cfg.egrabber_frame_buffer)  # allocate RAM buffer N frames
        self.log.info(f"buffer set to: {frame_count} frames")

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

    def start(self, frame_count: int = 1, live: bool = False):
        if live:
            self.grabber.start()
        else:
            self.grabber.start(frame_count)

    def stop(self):
        self.grabber.stop()

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
            return image

    def collect_background(self, frame_average = 1):
        """Retrieve a background image as a 2D numpy array with shape (rows, cols). """
        # Note: the background image is optionally averaged
        if self.grabber.remote.get("TriggerMode") != "Off":  # set camera to internal trigger mode
            self.grabber.remote.set("TriggerMode", "Off")
        # Initialize background image array
        bkg_image = numpy.zeros((frame_average, self.cfg.sensor_row_count, self.cfg.sensor_column_count), dtype='uint16')
        # Grab N background images
        self.start(frame_count = frame_average, live = False)
        for frame in range(0, frame_average):
            self.log.info(f"Capturing background image: {frame}")
            bkg_image[frame] = self.grab_frame()
        self.log.info(f"Averaging {frame_average} background images")
        self.stop()
        if self.grabber.remote.get("TriggerMode") != "On":  # set camera to external trigger mode
            self.grabber.remote.set("TriggerMode", "On")
        # Return median averaged 2D background image
        return numpy.median(bkg_image, axis = 0).astype('uint16')

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

    def log_metadata(self):
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
                            self.log.info(f'device, {feature}, {self.grabber.device.get(feature)}')

        categories = self.grabber.remote.get(query.categories())
        for category in categories:
            features = self.grabber.remote.get(query.features_of(category))
            for feature in features:
                if self.grabber.remote.get(query.available(feature)):
                    if self.grabber.remote.get(query.readable(feature)):
                        if not self.grabber.remote.get(query.command(feature)):
                            if feature != "BalanceRatioSelector" and feature != "BalanceWhiteAuto":
                                self.log.info(f'remote, {feature}, {self.grabber.remote.get(feature)}')

        categories = self.grabber.stream.get(query.categories())
        for category in categories:
            features = self.grabber.stream.get(query.features_of(category))
            for feature in features:
                if self.grabber.stream.get(query.available(feature)):
                    if self.grabber.stream.get(query.readable(feature)):
                        if not self.grabber.stream.get(query.command(feature)):
                            self.log.info(f'stream, {feature}, {self.grabber.stream.get(feature)}')

        categories = self.grabber.interface.get(query.categories())
        for category in categories:
            features = self.grabber.interface.get(query.features_of(category))
            for feature in features:
                if self.grabber.interface.get(query.available(feature)):
                    if self.grabber.interface.get(query.readable(feature)):
                        if not self.grabber.interface.get(query.command(feature)):
                            self.log.info(f'interface, {feature}, {self.grabber.interface.get(feature)}')

        categories = self.grabber.system.get(query.categories())
        for category in categories:
            features = self.grabber.system.get(query.features_of(category))
            for feature in features:
                if self.grabber.system.get(query.available(feature)):
                    if self.grabber.system.get(query.readable(feature)):
                        if not self.grabber.system.get(query.command(feature)):
                            self.log.info(f'system, {feature}, {self.grabber.system.get(feature)}')
