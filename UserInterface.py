import time
import threading
import os
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
import config as cfg
from tifffile import imwrite
from magicclass import magicclass, set_design, MagicTemplate
from magicgui import magicgui, widgets
from napari.qt.threading import thread_worker
from skimage.transform import downscale_local_mean
from tigerasi.tiger_controller import TigerController
from enum import Enum

@magicclass(labels=False)
class UserInterface(MagicTemplate):

    def __init__(self):

        self.cfg = cfg

    def _startup(self):

        self.camera = Camera.Camera()
        self.waveform_generator = WaveformGenerator.WaveformGenerator()
        self.data_writer = DataWriter.DataWriter()
        self.data_processor = DataProcessor.DataProcessor()
        self.file_transfer = FileTransfer.FileTransfer()
        self.data_logger = DataLogger.DataLogger()

    def _update_fps(self, fps):

        self.viewer.text_overlay.text = f"{fps:1.1f} FPS"

    def _set_viewer(self, viewer):

        self.viewer=viewer
        self.viewer.text_overlay.visible = True
        self.viewer.window.qt_viewer.canvas.measure_fps(callback=self._update_fps)       
        self.viewer.scale_bar.visible = True
        self.viewer.scale_bar.unit = "um"
        self.cmaps=['gray', 'green', 'magenta', 'cyan', 'yellow', 'red', 'blue']

    def _set_worker_live(self, worker_live):

        self.worker_live=worker_live
        self.worker_live_started=False
        self.worker_live_running=False

    def _set_worker_record(self, worker_record):

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
            self.viewer.layers['Camera ' + str(cam)]._slice.image._view=image
            self.viewer.layers['Camera ' + str(cam)].events.set_data()
        except:
            self.viewer.add_image(image, name='Camera', blending='additive', colormap=self.cmaps[cam], scale=(self.scaleX, self.scaleY))

        self.viewer.layers['Camera ' + str(cam)].contrast_limits=(0, 200)

        if self.cfg.autoscale == True:
            self.viewer.layers['Camera ' + str(cam)].contrast_limits=(0, numpy.amax(image))

    def _display_preprocess(self, image):

        if self.cfg.method == 'downscale_mean':
            image = downscale_local_mean(images, (8,8))

        if self.cfg.method == 'decimate':
            image = image[0::8, 0::8]

        if self.cfg.method == 'downscale_max':
            N = 3
            for i in range(0,N):
                temp = numpy.zeros((4, int(image.shape[0]/2), int(image.shape[1]/2)), dtype = self.cfg.datatype)
                temp[0] = image[0::2,0::2]
                temp[1] = image[1::2,0::2]
                temp[2] = image[0::2,1::2]
                temp[3] = image[1::2,1::2]
                image = numpy.amax(temp, axis = 0, keepdims = False)

        if self.cfg.method == 'decimate_mean':
            N = 3
            for i in range(0,N):
                image = 0.25*(image[0::2,0::2]+image[1::2,0::2]+image[0::2,1::2]+image[1::2,1::2]).astype(self.cfg.datatype)

        if self.cfg.method == 'corners':
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

        if self.cfg.method == 'center':
            height = 1330
            width = 1774
            image = image[int(self.cfg.cam_y/2-height/2):int(self.cfg.cam_y/2+height/2), int(self.cfg.cam_x/2-width/2):int(self.cfg.cam_x/2+width/2)]

        if self.cfg.method == 'full':
            image = image

        return image

    @thread_worker
    def _acquire_live(self):

        frame_num = 0
        while True:
            image = self.camera.grab_frame()
            frame_num += 1
            if frame_num % 4 == 0:
                yield image

    @thread_worker
    def _acquire_record(self):

        for tile in range(0, self.cfg.n_tiles):

            self.cfg.filename = self.cfg.filename + '_' + str(tile)

            images = numpy.zeros((self.cfg.chunk_size,self.cfg.cam_y,self.cfg.cam_x), dtype=self.cfg.datatype)
            mip = numpy.zeros((self.cfg.cam_y,self.cfg.cam_x), dtype=self.cfg.datatype)

            frame_num = 0
            buffer_frame_num = 0
            chunk_num = 0

            self.camera.configure(self.cfg)
            self.waveform_generator.configure(self.cfg, live = False)
            self.waveform_generator.generate_waveforms(live = False)
            self.data_writer.configure(self.cfg)
            self.data_processor.configure(self.cfg)
            self.data_logger.configure(self.cfg)

            self.data_logger.start()

            try:

                start_time = time.time()

                self.camera.start(live = False)

                while frame_num < n_frames:

                    if frame_num == 0:
                        self.waveform_generator.start(live = False)

                    image = camera.grab_frame()
                    images[buffer_frame_num] = image
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

                    yield image     

            finally:

                self.waveform_generator.stop()
                self.camera.stop()
                self.data_logger.stop()

                self.waveform_generator.close()
                self.data_writer.close()
                self.data_processor.close()
                self.data_logger.close()

                print('imaging time: ' + str((time.time()-start_time)/3600))

                # imwrite('D:\\tile_' + str(tile) + '_mip.tiff', mip) # TODO put this somewhere else. save mip tiff image

                # start_time = time.time()

                # if tile > 0:
                #     wait_start = time.time()
                #     file_transfer.wait()
                #     file_transfer.close()
                #     os.remove('D:\\' + 'tile_' + str(tile-1) + '.ims')
                #     os.remove('D:\\' + 'tile_' + str(tile-1) + '.memento')
                #     os.remove('D:\\' + 'tile_' + str(tile-1) + '_mip.tiff')
                #     print('wait time: ' + str((time.time() - wait_start)/3600))

                # file_transfer.start(['tile_' + str(tile) + '.memento', 'tile_' + str(tile) + '_mip.tiff', 'tile_' + str(tile) + '.ims'])

                # if tile == self.cfg.n_tiles-1:
                #     wait_start = time.time()
                #     file_transfer.wait()
                #     file_transfer.close()
                #     os.remove('D:\\' + 'tile_' + str(tile) + '.ims')
                #     os.remove('D:\\' + 'tile_' + str(tile) + '.memento')
                #     os.remove('D:\\' + 'tile_' + str(tile) + '_mip.tiff')
                #     print('wait time: ' + str((time.time() - wait_start)/3600))

    @magicgui(
        auto_call=True,
        live_display={"widget_type": "PushButton", "label": 'Live Display'},
        layout='horizontal'
    )
    def live_display(self, live_display=False):

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(2.0/self.FrameRate)
            self.camera.stop()
            self.waveform_generator.stop()
            self.waveform_generator.close()
        else:
            if not(self.worker_live_started):
                self.worker_live_started=True
                self.camera.configure(self.cfg)
                self.waveform_generator.configure(self.cfg, live = True)
                self.waveform_generator.generate_waveforms(live = True)
                self.camera.start(live = True)
                self.waveform_generator.start()
                self.worker_live.start()
                self.worker_live_running=True
            else:
                self.waveform_generator.configure(self.cfg, live = True)
                self.waveform_generator.generate_waveforms(live = True)
                self.camera.start(live = True)
                self.waveform_generator.start()
                self.worker_live.resume()
                self.worker_live_running=True

    @magicgui(
        auto_call=True,
        record={"widget_type": "PushButton", "label": 'Record'},
        layout='horizontal'
    )
    def record(self, record=False):

        if self.worker_record_running:
            self.worker_record.pause()
            self.worker_record_running=False 
            time.sleep(2.0/(self.FrameRate))
            self.camera.stop()
            self.waveform_generator.stop()
        else:
            if not(self.worker_record_started):
                self.worker_record_started=True
                self.worker_record.start()
                self.worker_record_running=True
            else:
                camera.start()
                waveform_generator.start()
                self.worker_record.resume()
                self.worker_record_running=True
        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False

    @magicgui(
        auto_call=True,
        etl_amplitude={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": 'ETL amplitude (V)'},
        etl_offset={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": 'ETL offset (V)'},
        camera_delay_time={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": 'Camera delay time (ms)'},
        etl_buffer_time={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": 'ETL buffer time (ms)'},
        rest_time={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": 'Stage settling time (ms)'},
        layout='vertical',
    )
    def set_waveform_param(self, etl_amplitude = self.cfg.etl_amlitude, etl_offset = self.cfg.etl_offset, camera_delay_time =  = self.cfg.camera_delay_time, etl_buffer_time =  = self.cfg.etl_buffer_time, rest_time =  = self.cfg.rest_time):
        
        print(etl_amlitude)
        print(etl_offset)
        print(camera_delay_time)
        print(etl_buffer_time)
        print(rest_time)

        self.cfg.etl_amlitude = etl_amplitude
        self.cfg.etl_offset = etl_offset
        self.cfg.camera_delay_time = camera_delay_time
        self.cfg.etl_buffer_time = etl_buffer_time
        self.cfg.rest_time = rest_time

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(2.0/self.FrameRate)
            self.camera.stop()
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(live = True)
            self.camera.start(live = True)
            self.waveform_generator.start()

        if self.worker_record_running:
            print('error')
            # throw error, don't change params during recording

    @magicgui(
        auto_call=True,
        active_channels = {"widget_type": "Select", "choices": ["Off","405","488","561","638"], "allow_multiple": False, "label": "Active channels"}
    )
    def set_channel_state(self, active_channels = self.cfg.channels):

        print(active_channels)

        channels = {'405': False, '488': False, '561': False, '648': False}
        for channel in active_channels:
            if channel == 'Off':
                states = [False,False,False,False]
                break
            if channel == '405':
                states['405']=True
            elif channel == '488':
                states['488']=True
            elif channel == '561':
                states['561']=True
            elif channel == '638':
                states['638']=True

        self.cfg.channels = channels

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(2.0/self.FrameRate)
            self.camera.stop()
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(live = True)
            self.camera.start(live = True)
            self.waveform_generator.start()

        if self.worker_record_running:
            print('error')
            # throw error, don't change params during recording

    @magicgui(
        auto_call=True,
        power_405={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": '405nm power (%)'},
        power_488={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": '488nm power (%)'},
        power_561={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": '561nm power (%)'},
        power_638={"widget_type": "FloatSpinBox", "min": 0, "max": 100, "label": '635nm power (%)'},
        layout='vertical',
    )
    def set_channel_power(self, power_405 = self.cfg.channel_powers['405'], power_488 = self.cfg.channel_powers['488'], power_561 = self.cfg.channel_powers['561'], power_638 = self.cfg.channel_powers['638']):

        print(power_405)
        print(power_488)
        print(power_561)
        print(power_638)

        channel_powers['405'] = power_405
        channel_powers['488'] = power_488
        channel_powers['561'] = power_561
        channel_powers['638'] = power_638

        self.cfg.channel_powers = channel_powers

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(2.0/self.FrameRate)
            self.camera.stop()
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(live = True)
            self.camera.start(live = True)
            self.waveform_generator.start()

        if self.worker_record_running:
            print('error')
            # throw error, don't change params during recording

    @magicgui(
        auto_call=True,
        exposure_ms={"widget_type": "FloatSpinBox", "min": 1, "max": 50,'label': 'Camera exposure (ms)'},
        layout='horizontal',
    )
    def set_exposure(self, exposure_ms = self.cfg.dwell_time):

        print(exposure_ms)

        self.cfg.dwell_time = exposure_ms

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(2.0/self.FrameRate)
            self.camera.stop()
            self.waveform_generator.stop()
            self.waveform_generator.close()
            self.waveform_generator.configure(self.cfg, live = True)
            self.waveform_generator.generate_waveforms(live = True)
            self.camera.start(live = True)
            self.waveform_generator.start()

        if self.worker_record_running:
            print('error')
            # throw error, don't change params during recording

    @magicgui(
        auto_call=True,
        source_path={"widget_type": "FileEdit","mode": "d", "label": 'Local path:'},
        layout='horizontal', 
    )
    def set_save_path(self, source_path = self.cfg.source_path):

        print(source_path)

        self.cfg.source_path = source_path

    @magicgui(
        auto_call=True,
        mode={"choices": ["center", "full", "downscale_mean", "decimate_mean", "downscale_max", "corners"]},
        layout='horizontal'
    )
    def set_display_method(self, mode = self.cfg.method):

        print(mode)

        self.cfg.method = mode
        self.viewer.reset_view()

        print(self.viewer.camera.center)
        print(self.viewer.camera.zoom)