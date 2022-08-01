import time
import threading
import os
import sys
import time
import os.path
import traceback
import time
import glob
import config
import Camera
import WaveformGenerator
import DataWriter
import DataProcessor
import FileTransfer
import DataLogger
import thorlabs_apt as RotationStage
import numpy
from tifffile import imwrite
from magicclass import magicclass, set_design, MagicTemplate
from magicgui import magicgui, widgets
from napari.qt.threading import thread_worker
from skimage.transform import downscale_local_mean

@magicclass(labels=False)
class UserInterface(MagicTemplate):

    # initialize
    def __init__(self):
        
        self.cfg = config.config()
        self._initialize_hardware()
        if not os.path.exists(self.cfg.source_path):
            os.makedirs(self.cfg.source_path)
        if not os.path.exists(self.cfg.destination_path):
            os.makedirs(self.cfg.destination_path)        

    def _initialize_hardware(self):

        self.camera = Camera.Camera()
        self.waveform_generator = WaveformGenerator.WaveformGenerator()
        self.data_writer = DataWriter.DataWriter()
        self.data_processor = DataProcessor.DataProcessor()
        self.file_transfer = FileTransfer.FileTransfer()
        self.data_logger = DataLogger.DataLogger()
        # self.rotation_stage = RotationStage.Motor(55271274)

    def _configure_hardware(self, live):

        self.camera.configure(self.cfg)
        self.waveform_generator.configure(self.cfg, live = live)
        self.waveform_generator.generate_waveforms(live = live)

    def _start_hardware(self, live = False):

        self.camera.start(live = live)
        self.waveform_generator.start()

    def _stop_hardware(self):

        self.camera.stop()
        self.waveform_generator.stop()
        self.waveform_generator.close()

    def _update_fps(self, fps):
        """Update fps."""
        self.viewer.text_overlay.text = f"{fps:1.1f} FPS"

    # set viewer
    def _set_viewer(self, viewer):
        """
        Set Napari viewer
        :param viewer: Viewer
            Napari viewer
        :return None:
        """

        self.viewer=viewer
        self.viewer.text_overlay.visible = True
        self.viewer.window.qt_viewer.canvas.measure_fps(callback=self._update_fps)       
        self.viewer.scale_bar.visible = True
        self.viewer.scale_bar.unit = "um"
        self.cmaps=['gray', 'green', 'magenta', 'cyan', 'yellow', 'red', 'blue']

    # set live_display acquistion thread worker
    def _set_worker_live(self, worker_live):
        """
        Set worker for live live_display display
        :param worker_live_display: thread_worker
            Napari thread worker
        :return None:
        """

        self.worker_live=worker_live
        self.worker_live_started=False
        self.worker_live_running=False

    # set h5 record thread worker
    def _set_worker_record(self, worker_record):
        """
        Set h5 worker for record
        :param worker_record: thread_worker
            h5 record thread worker
        :return None:
        """

        self.worker_record=worker_record
        self.worker_record_started=False
        self.worker_record_running=False

    def _update_display(self, image):

        image = self._display_preprocess(image)

        # pyramid = []
        # resolutions = [1, 2, 4, 8, 16]
        # for downscale in resolutions:
        #     images = images[0::2, 0::2]
        #     pyramid.append(images)

        try:
            self.viewer.layers['Camera']._slice.image._view=image
            self.viewer.layers['Camera'].events.set_data()
        except:
            self.viewer.add_image(image, name='Camera', blending='additive', colormap=self.cmaps[0], scale=(self.cfg.scale_x, self.cfg.scale_y))

        # self.viewer.layers['Camera'].contrast_limits=(0, 200)

        if self.cfg.autoscale == True:
            self.viewer.layers['Camera'].contrast_limits=(0, numpy.amax(image))

    def _display_preprocess(self, image):

        if self.cfg.method == 'Downscale mean':
            image = downscale_local_mean(image, (8,8))

        if self.cfg.method == 'Decimate':
            image = image[0::8, 0::8]

        if self.cfg.method == 'Downscale max':
            N = 3
            for i in range(0,N):
                temp = numpy.zeros((4, int(image.shape[0]/2), int(image.shape[1]/2)), dtype = self.cfg.datatype)
                temp[0] = image[0::2,0::2]
                temp[1] = image[1::2,0::2]
                temp[2] = image[0::2,1::2]
                temp[3] = image[1::2,1::2]
                image = numpy.amax(temp, axis = 0, keepdims = False)

        if self.cfg.method == 'Decimate mean':
            N = 3
            for i in range(0,N):
                image = 0.25*(image[0::2,0::2]+image[1::2,0::2]+image[0::2,1::2]+image[1::2,1::2]).astype(self.cfg.datatype)

        if self.cfg.method == 'Corners':
            width = 591
            height = 443
            border = 10
            temp = numpy.zeros((3*height,3*width), dtype = self.cfg.datatype)
            temp[0:height,0:width] = image[0:height,0:width]
            temp[height:2*height,0:width] = image[int(self.cfg.cam_y/2-height/2):int(self.cfg.cam_y/2+height/2),0:width]
            temp[2*height:3*height,0:width] = image[self.cfg.cam_y-height:self.cfg.cam_y,0:width]
            temp[0:height,width:2*width] = image[0:height,int(self.cfg.cam_x/2-width/2):int(self.cfg.cam_x/2+width/2)]
            temp[height:2*height,width:2*width] = image[int(self.cfg.cam_y/2-height/2):int(self.cfg.cam_y/2+height/2),int(self.cfg.cam_x/2-width/2):int(self.cfg.cam_x/2+width/2)]
            temp[2*height:3*height,width:2*width] = image[self.cfg.cam_y-height:self.cfg.cam_y,int(self.cfg.cam_x/2-width/2):int(self.cfg.cam_x/2+width/2)]
            temp[0:height,2*width:3*width] = image[0:height,self.cfg.cam_x-width:self.cfg.cam_x]
            temp[height:2*height,2*width:3*width] = image[int(self.cfg.cam_y/2-height/2):int(self.cfg.cam_y/2+height/2),self.cfg.cam_x-width:self.cfg.cam_x]
            temp[2*height:3*height,2*width:3*width] = image[self.cfg.cam_y-height:self.cfg.cam_y,self.cfg.cam_x-width:self.cfg.cam_x]
            temp[height-border:height,:] = 0
            temp[2*height:2*height+border,:] = 0
            temp[:,width-border:width] = 0
            temp[:,2*width:2*width+border] = 0
            image = temp

        if self.cfg.method == 'Center':
            height = 1330
            width = 1774
            image = image[int(self.cfg.cam_y/2-height/2):int(self.cfg.cam_y/2+height/2), int(self.cfg.cam_x/2-width/2):int(self.cfg.cam_x/2+width/2)]

        if self.cfg.method == 'ASLM':
            image = image[0::8, 7096-887:7096+887]

        if self.cfg.method == 'Full':
            image = image

        return image

    @thread_worker
    def _acquire_live(self):

        while True:
            image = self.camera.grab_frame()
            yield image

    @thread_worker
    def _acquire_record(self):

        for x_tile in range(0, self.cfg.x_tiles):

            for y_tile in range(0, self.cfg.y_tiles):

                for ch in range(0, self.cfg.n_channels):

                    tile_num = ch + y_tile*self.cfg.n_channels + self.cfg.n_channels*self.cfg.y_tiles*x_tile

                    print(tile_num)

                    tile_name = 'tile_x_{:0>4d}_y_{:0>4d}_z_{:0>4d}_ch_{:0>4d}'.format(x_tile, y_tile, 0, ch)

                    print(x_tile*self.cfg.cam_x*self.cfg.pixel_x*(1-self.cfg.x_overlap/100))
                    print(y_tile*self.cfg.cam_y*self.cfg.pixel_y*(1-self.cfg.y_overlap/100))

                    images = numpy.zeros((self.cfg.chunk_size,self.cfg.cam_y,self.cfg.cam_x), dtype=self.cfg.datatype)
                    mip = numpy.zeros((self.cfg.cam_y,self.cfg.cam_x), dtype=self.cfg.datatype)

                    frame_num = 0
                    buffer_frame_num = 0
                    chunk_num = 0

                    self._configure_hardware(live = False)

                    self.data_writer.configure(self.cfg, tile_name)
                    self.data_processor.configure(self.cfg)
                    self.data_logger.configure(self.cfg, tile_name)
                    self.file_transfer.configure(self.cfg)

                    self.data_logger.start()

                    try:

                        start_time = time.time()

                        self.camera.start(live = False)

                        while frame_num < self.cfg.n_frames:

                            if frame_num == 0:
                                self.waveform_generator.start()

                            image = self.camera.grab_frame()
                            images[buffer_frame_num] = image
                            frame_num += 1
                            buffer_frame_num += 1

                            # self.camera.print_statistics()

                            if buffer_frame_num % self.cfg.chunk_size == 0:
                                self.data_writer.write_block(images, chunk_num)
                                if frame_num > self.cfg.chunk_size:
                                    mip = self.data_processor.update_max_project(mip)
                                self.data_processor.max_project(images)
                                buffer_frame_num = 0
                                chunk_num += 1

                            elif frame_num == self.cfg.n_frames:
                                self.data_writer.write_block(images, chunk_num)
                                self.data_processor.max_project(images)
                                mip = self.data_processor.update_max_project(mip)  

                    finally:

                        yield mip

                        self.waveform_generator.stop()
                        self.camera.stop()
                        self.data_logger.stop()

                        self.waveform_generator.close()
                        self.data_writer.close(x_tile, y_tile)
                        self.data_processor.close()
                        self.data_logger.close()

                        print('imaging time: ' + str((time.time()-start_time)/3600))

                        imwrite(self.cfg.source_path + tile_name + '_mip.tiff', mip) # TODO put this somewhere else. save mip tiff image

                        start_time = time.time()

                        if tile_num > 0:
                            wait_start = time.time()
                            self.file_transfer.wait()
                            self.file_transfer.close()
                            os.remove(self.cfg.source_path + previous_tile_name + '.ims')
                            os.remove(self.cfg.source_path + previous_tile_name + '.memento')
                            os.remove(self.cfg.source_path + previous_tile_name + '_mip.tiff')
                            print('wait time: ' + str((time.time() - wait_start)/3600))

                        self.file_transfer.start([tile_name + '.memento', tile_name + '_mip.tiff', tile_name + '.ims'])

                        if tile_num == self.cfg.x_tiles*self.cfg.y_tiles*self.cfg.n_channels-1:
                            wait_start = time.time()
                            self.file_transfer.wait()
                            self.file_transfer.close()
                            os.remove(self.cfg.source_path + tile_name +  '.ims')
                            os.remove(self.cfg.source_path + tile_name + '.memento')
                            os.remove(self.cfg.source_path + tile_name + '_mip.tiff')
                            print('wait time: ' + str((time.time() - wait_start)/3600))

                        previous_tile_name = tile_name

    @magicgui(
        auto_call=True,
        live_display={"widget_type": "PushButton", "label": 'Live Display'},
        layout='horizontal'
    )
    def live_display(self, live_display=False):

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(1.1*(self.cfg.total_time/1000.0))
            self._stop_hardware()
        else:
            if not(self.worker_live_started):
                self._configure_hardware(live = True)
                self._start_hardware(live = True)
                self.worker_live.start()
                self.worker_live_started=True
                self.worker_live_running=True
            else:
                self._configure_hardware(live = True)
                self._start_hardware()
                self.worker_live.resume()
                self.worker_live_running=True

    @magicgui(
        auto_call=True,
        record={"widget_type": "PushButton", "label": 'Record HDF5'},
        layout='horizontal'
    )
    def record(self, record=False):

        if self.worker_record_running:
            print('acquisition in progress')
        else:
            if not(self.worker_record_started):
                self.worker_record_started=True
                self.worker_record_running=True
                self.worker_record.start()
            else:
                print('acquisition in progress')
        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        etl_amplitude={"widget_type": "FloatSpinBox", "min": -1, "max": 1, "step": 0.001, "label": 'ETL amplitude (V)'},
        etl_offset={"widget_type": "FloatSpinBox", "min": 0, "max": 5, "step": 0.001, "label": 'ETL offset (V)'},
        etl_nonlinear={"widget_type": "FloatSpinBox", "min": -0.02, "max": 0.02, "step": 0.001, "label": 'ETL nonlinear (V)'},
        etl_interp_time={"widget_type": "FloatSpinBox", "min": 0, "max": 1, "step": 0.001, "label": 'ETL interp time (%)'},
        camera_delay_time={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.001, "label": 'Camera delay time (ms)'},
        etl_buffer_time={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.001, "label": 'ETL buffer time (ms)'},
        laser_buffer_time={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.001, "label": 'Laser buffer time (ms)'},
        rest_time={"widget_type": "FloatSpinBox", "min": 0, "max": 1000, "step": 0.001, "label": 'Stage settling time (ms)'},
        layout='vertical',
    )
    def set_waveform_param(self, etl_amplitude = config.config().etl_amplitude, etl_offset = config.config().etl_offset, etl_nonlinear = config.config().etl_nonlinear, etl_interp_time = config.config().etl_interp_time, camera_delay_time = config.config().camera_delay_time, etl_buffer_time = config.config().etl_buffer_time, laser_buffer_time = config.config().laser_buffer_time, rest_time = config.config().rest_time):

        self.cfg.etl_amplitude = etl_amplitude
        self.cfg.etl_offset = etl_offset
        self.cfg.etl_nonlinear = etl_nonlinear
        self.cfg.etl_interp_time = etl_interp_time
        self.cfg.camera_delay_time = camera_delay_time
        self.cfg.etl_buffer_time = etl_buffer_time
        self.cfg.laser_buffer_time = laser_buffer_time
        self.cfg.rest_time = rest_time

        if self.worker_live_running:
            # self.worker_live.pause()
            # self.worker_live_running=False
            # time.sleep(1.1*(self.cfg.total_time/1000.0))
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(self.cfg)
            self.waveform_generator.start()
            # self._stop_hardware()
            # self._configure_hardware(live = True)
            # self._start_hardware(live = True)
            # self.worker_live.resume()
            # self.worker_live_running=True


    @magicgui(
        auto_call=True,
        active_channels = {"widget_type": "Select", "choices": ["Off","405","488","561","638"], "allow_multiple": False, "label": "Active channels"},
        layout='vertical'
    )
    def set_channel_state(self, active_channels):

        # for channel in active_channels:
        #     if channel == 'Off':
        #         states = [False,False,False,False]
        #         break
        #     if channel == '405':
        #         states['405']=True
        #     elif channel == '488':
        #         states['488']=True
        #     elif channel == '561':
        #         states['561']=True
        #     elif channel == '638':
        #         states['638']=True

        # self.cfg.channels = channels

        pass

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        power_405={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '405nm power (%)'},
        power_488={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '488nm power (%)'},
        power_561={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '561nm power (%)'},
        power_638={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '635nm power (%)'},
        layout='vertical',
    )
    def set_channel_power(self, power_405 = config.config().channel_powers['405'], power_488 = config.config().channel_powers['488'], power_561 = config.config().channel_powers['561'], power_638 = config.config().channel_powers['638']):

        channel_powers['405'] = power_405
        channel_powers['488'] = power_488
        channel_powers['561'] = power_561
        channel_powers['638'] = power_638

        self.cfg.channel_powers = channel_powers

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        exposure_ms={"widget_type": "FloatSpinBox", "min": 1, "max": 100,"step": 0.01, 'label': 'Camera exposure (ms)'},
        layout='horizontal',
    )
    def set_exposure(self, exposure_ms = config.config().dwell_time):

        self.cfg.dwell_time = exposure_ms

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        rotation={"widget_type": "FloatSpinBox", "min": 0, "max": 360,"step": 0.01, 'label': 'Light sheet angle (deg)'},
        layout='horizontal',
    )
    def set_rotation(self, rotation = 0):

        self.rotation_stage.move_to(rotation)

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        source_path={"widget_type": "FileEdit","mode": "d", "label": 'Local path:'},
        layout='horizontal', 
    )
    def set_save_path(self, source_path = config.config().source_path):

        self.cfg.source_path = source_path

    @magicgui(
        auto_call=True,
        Display={"choices": ["Center", "Decimate", "Corners", "Downscale mean", "Decimate mean", "Downscale max", "Full", "ASLM"]},
        layout='horizontal'
    )
    def set_display_method(self, Display = config.config().method):

        self.cfg.method = Display
        self.viewer.reset_view()

        # print(self.viewer.camera.center)
        # print(self.viewer.camera.zoom)