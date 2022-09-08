import time
import threading
import os
import sys
import time
import os.path
import traceback
import time
import glob
from exaspim.devices import Camera
from exaspim.devices import WaveformGenerator
from exaspim.processes import DataWriter
from exaspim.processes import DataProcessor
from exaspim.processes import FileTransfer
from exaspim.processes import DataLogger
# import thorlabs_apt as RotationStage
import numpy
from exaspim.config import config
from tifffile import imwrite
from magicclass import magicclass, set_design, MagicTemplate
from magicgui import magicgui, widgets, FunctionGui
from napari.qt.threading import thread_worker
from skimage.transform import downscale_local_mean
from tigerasi.tiger_controller import TigerController, UM_TO_STEPS
from math import ceil

@magicclass(labels=False)
class UserInterface(MagicTemplate):

    def __init__(self):
        
        self.cfg = config()
        self._initialize_hardware()   

    def _initialize_hardware(self):

        self.camera = Camera.Camera()
        self.waveform_generator = WaveformGenerator.WaveformGenerator()
        self.data_writer = {}
        self.data_processor = {}
        self.file_transfer = {}
        for ch in self.cfg.channels:
            self.data_writer[ch] = DataWriter.DataWriter()
            self.data_processor[ch] = DataProcessor.DataProcessor()
        self.file_transfer = FileTransfer.FileTransfer()
        self.data_logger = DataLogger.DataLogger()
        # self.rotation_stage = RotationStage.Motor(55271274)
        # self.xyz_stage = TigerController('COM3')

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

        self.viewer.text_overlay.text = f"{fps:1.1f} FPS"

    def _set_viewer(self, viewer):

        self.viewer=viewer
        self.viewer.text_overlay.visible = True
        self.viewer.window.qt_viewer.canvas.measure_fps(callback=self._update_fps)       
        self.viewer.scale_bar.visible = True
        self.viewer.scale_bar.unit = "um"
        self.cmaps=     {   
                            '405': 'gray',
                            '488': 'green',
                            '561': 'cyan',
                            '638': 'magenta'
                        }

    def _set_worker_live(self, worker_live):

        self.worker_live=worker_live
        self.worker_live_started=False
        self.worker_live_running=False

    def _set_worker_record(self, worker_record):

        self.worker_record=worker_record
        self.worker_record_started=False
        self.worker_record_running=False

    def _reset_display(self):

        self.viewer.layers.clear()

    def _update_display(self, values):

        channels = values[0]
        images = values[1]

        for ch in channels:

            pyramid = []
            resolutions = [1, 2, 4, 8, 16]
            for downscale in resolutions:
                pyramid.append(images[ch][0::downscale, 0::downscale])

            try:
                self.viewer.layers[ch].data = pyramid
            except:
                self.viewer.add_image(pyramid, name=ch, blending='additive', colormap=self.cmaps[ch], scale=(self.cfg.scale_x, self.cfg.scale_y))

            if self.cfg.autoscale == True:
                self.viewer.layers[ch].contrast_limits=(0, numpy.amax(image))

    @thread_worker
    def _acquire_live(self):

        images = {}

        while True:
            for ch in self.cfg.channels:
                images[ch] = self.camera.grab_frame()
            yield self.cfg.channels, images

    @thread_worker
    def _acquire_record(self):

        if not os.path.exists(self.cfg.source_path):
            os.makedirs(self.cfg.source_path)
        if not os.path.exists(self.cfg.destination_path):
            os.makedirs(self.cfg.destination_path)  

        print('y step: ' + str(self.cfg.y_grid_step_um))
        print('z step: ' + str(self.cfg.z_grid_step_um))

        print('z tiles ' + str(self.cfg.z_tiles))
        print('y tiles ' + str(self.cfg.y_tiles))

        stage_x_pos, stage_y_pos, stage_z_pos = (0, 0, 0)
        # self.xyz_stage.set_axis_backlash(x=0.0)

        for z_tile in range(0, self.cfg.z_tiles):

            # self.xyz_stage.move_axes_absolute(z=round(stage_z_pos))

            stage_y_pos = 0

            for y_tile in range(0, self.cfg.y_tiles):

                tile_name = {}
                for ch in self.cfg.channels:
                    tile_name[ch] = ('tile_x_{:0>4d}_y_{:0>4d}_z_{:0>4d}_ch_' + str(ch)).format(y_tile, z_tile, 0)

                tile_num = y_tile*self.cfg.n_channels + self.cfg.n_channels*self.cfg.y_tiles*z_tile

                # self.xyz_stage.move_axes_absolute(y=round(stage_y_pos))

                stage_x_pos = 0

                print('y_tile: ' + str(y_tile))
                print('z_tile: ' + str(z_tile))
                print('x: ' + str(stage_x_pos))
                print('y: ' + str(stage_y_pos))
                print('z: ' + str(stage_z_pos))

                # self.xyz_stage.set_axis_backlash(x=1.0)
                # self.xyz_stage.move_axes_absolute(x=round(stage_x_pos))

                # while self.xyz_stage.is_moving():
                #     # print('waiting')
                #     time.sleep(0.1)
                #     pass

                self._configure_hardware(live = False)

                images = {}
                mip = {}
                for ch in self.cfg.channels:
                    images[ch] = numpy.zeros((self.cfg.chunk_size, self.cfg.cam_y,self.cfg.cam_x), dtype=self.cfg.datatype)
                    mip[ch] = numpy.zeros((self.cfg.cam_y,self.cfg.cam_x), dtype=self.cfg.datatype)
                    self.data_writer[ch].configure(self.cfg, tile_name[ch])
                    self.data_processor[ch].configure(self.cfg)

                self.file_transfer.configure(self.cfg)
                self.data_logger.configure(self.cfg, tile_name['488'])

                frame_num = 0
                buffer_frame_num = 0
                chunk_num = 0

                try:

                    start_time = time.time()

                    self.data_logger.start()

                    self.camera.start(live = False)

                    while frame_num < self.cfg.n_frames:

                        if frame_num == 0:
                            self.waveform_generator.start()

                        for ch in self.cfg.channels:
                            image = self.camera.grab_frame()
                            images[ch][buffer_frame_num] = image
                            self.camera.print_statistics(ch)

                        frame_num += 1
                        buffer_frame_num += 1

                        if buffer_frame_num % self.cfg.chunk_size == 0:

                            for ch in self.cfg.channels:
                                self.data_writer[ch].write_block(images[ch], chunk_num)
                                if frame_num > self.cfg.chunk_size:
                                    mip[ch] = self.data_processor[ch].update_max_project(mip[ch])
                                self.data_processor[ch].max_project(images[ch])

                            buffer_frame_num = 0
                            chunk_num += 1

                        elif frame_num == self.cfg.n_frames:

                            for ch in self.cfg.channels:
                                self.data_writer[ch].write_block(images[ch], chunk_num)
                                self.data_processor[ch].max_project(images[ch])
                                mip[ch] = self.data_processor[ch].update_max_project(mip[ch])

                finally:

                    yield self.cfg.channels, mip

                    self.waveform_generator.stop()
                    self.camera.stop()
                    self.data_logger.stop()

                    self.waveform_generator.close()
                    self.data_logger.close()

                    for ch in self.cfg.channels:
                        self.data_writer[ch].close(ch, y_tile, z_tile)
                        self.data_processor[ch].close()

                    print('imaging time: ' + str((time.time()-start_time)/3600))

                    for ch in self.cfg.channels:
                        imwrite(self.cfg.source_path + tile_name[ch] + '_mip.tiff', mip[ch])

                    if tile_num > 0:
                        self.file_transfer.wait()
                        self.file_transfer.close()
                        for ch in self.cfg.channels:
                            os.remove(self.cfg.source_path + previous_tile_name[ch] + '.ims')
                            os.remove(self.cfg.source_path + previous_tile_name[ch] + '_mip.tiff')

                    self.file_transfer.start('tile_x_{:0>4d}_y_{:0>4d}_z_{:0>4d}'.format(y_tile, z_tile, 0))

                    if tile_num == self.cfg.z_tiles*self.cfg.y_tiles-1:
                        self.file_transfer.wait()
                        self.file_transfer.close()
                        for ch in self.cfg.channels:
                            os.remove(self.cfg.source_path + tile_name[ch] +  '.ims')
                            os.remove(self.cfg.source_path + tile_name[ch] + '_mip.tiff')

                    previous_tile_name = tile_name

                stage_y_pos += self.cfg.y_grid_step_um * UM_TO_STEPS

            stage_z_pos += self.cfg.z_grid_step_um * UM_TO_STEPS

    @magicgui(
        auto_call=True,
        live_display={"widget_type": "PushButton", "label": 'Live Display'},
        layout='horizontal'
    )
    def live_display(self, live_display=False):

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(0.5)
            self._stop_hardware()
        else:
            if not(self.worker_live_started):
                self._reset_display()
                self._configure_hardware(live = True)
                self.camera.start()
                self.waveform_generator.start()
                self.worker_live.start()
                self.worker_live_started=True
                self.worker_live_running=True
            else:
                self._reset_display()
                self._configure_hardware(live = True)
                self.camera.start()
                self.waveform_generator.start()
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
                self._reset_display()
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
    def set_waveform_param(self, etl_amplitude=config().etl_amplitude['488'], etl_offset=config().etl_offset['488'],
                           etl_nonlinear=config().etl_nonlinear['488'], etl_interp_time=config().etl_interp_time['488'],
                           camera_delay_time=config().camera_delay_time['488'], etl_buffer_time =config().etl_buffer_time['488'],
                           laser_buffer_time=config().laser_buffer_time['488'], rest_time=config().rest_time):

        self.cfg.etl_amplitude['488'] = etl_amplitude
        self.cfg.etl_offset['488'] = etl_offset
        self.cfg.etl_nonlinear['488'] = etl_nonlinear
        self.cfg.etl_interp_time['488'] = etl_interp_time
        self.cfg.camera_delay_time['488'] = camera_delay_time
        self.cfg.etl_buffer_time['488'] = etl_buffer_time
        self.cfg.laser_buffer_time['488'] = laser_buffer_time
        self.cfg.rest_time['488'] = rest_time

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(0.5)
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(self.cfg)
            self.camera.start()
            self.waveform_generator.start()            
            self.worker_live.resume()
            self._reset_display()
            self.worker_live_running=True

    @magicgui(
        auto_call=True,
        active_channels = {"widget_type": "Select", "choices": ["405","488","561","638"], "allow_multiple": True, "label": "Active channels"},
        layout='vertical'
    )
    def set_channel_state(self, active_channels):

        channels = []
        for ch in active_channels:
            channels.append(ch)

        self.cfg.channels = channels

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(0.5)
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(self.cfg)
            self.camera.start()
            self.waveform_generator.start()            
            self.worker_live.resume()
            self._reset_display()
            self.worker_live_running=True

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        power_405={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '405nm power (%)'},
        power_488={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '488nm power (%)'},
        power_561={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '561nm power (%)'},
        power_638={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "step": 0.1, "label": '635nm power (%)'},
        layout='vertical',
    )
    def set_channel_power(self, power_405 = config().channel_powers['405'], power_488 = config().channel_powers['488'], power_561 = config().channel_powers['561'], power_638 = config().channel_powers['638']):

        channel_powers['405'] = power_405
        channel_powers['488'] = power_488
        channel_powers['561'] = power_561
        channel_powers['638'] = power_638

        self.cfg.channel_powers = channel_powers

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        exposure_ms={"widget_type": "FloatSpinBox", "min": 0, "max": 100,"step": 0.01, 'label': 'Camera exposure (ms)'},
        layout='horizontal',
    )
    def set_exposure(self, exposure_ms=config().dwell_time):

        self.cfg.dwell_time = exposure_ms

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(0.5)
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(self.cfg)
            self.camera.start()
            self.waveform_generator.start()            
            self.worker_live.resume()
            self._reset_display()
            self.worker_live_running=True

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        rotation={"widget_type": "FloatSpinBox", "min": 0, "max": 360,"step": 0.01, 'label': 'Light sheet angle (deg)'},
        layout='horizontal',
    )
    def set_rotation(self, rotation = 40.5):

        self.cfg.rotation = rotation
        # self.rotation_stage.move_to(self.cfg.rotation)

    @magicgui(
        auto_call=False,
        call_button = 'Update',
        source_path={"widget_type": "FileEdit","mode": "d", "label": 'Local path:'},
        layout='horizontal', 
    )
    def set_save_path(self, source_path = config().source_path):

        self.cfg.source_path = source_path