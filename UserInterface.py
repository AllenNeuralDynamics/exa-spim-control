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
from tifffile import imwrite
from magicclass import magicclass, set_design, MagicTemplate
from magicgui import magicgui, widgets
from napari.qt.threading import thread_worker
from skimage.transform import downscale_local_mean

@magicclass(labels=False)
class UserInterface(MagicTemplate):

    # initialize
    def __init__(self):
        """
        initialize
        :return None:
        """
        # input parameters
        self.ROI_width_x=int(14192)       # unit: camera pixels
        self.ROI_width_y=int(10640)       # unit: camera pixels
        self.FrameRate=1                  # fps
        self.scaleX=0.748*16              # px/um scale factor
        self.scaleY=0.748*16              # px/um scale factor
        self.autoscale = False
        self.method='downscale_mean'

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

    # update viewer
    def _update_display(self, values):
        """
        Update Napari viewer
        :param values: tuple
            camera numnber
            image to update
        :return None:
        """

        cam=values[0]
        images=values[1]
        images = self._display_preprocess(images)

        # pyramid = []
        # resolutions = [1, 2, 4, 8, 16]
        # for downscale in resolutions:
        #     images = images[0::2, 0::2]
        #     pyramid.append(images)

        try:
            self.viewer.layers['Camera ' + str(cam)]._slice.image._view=images
            self.viewer.layers['Camera ' + str(cam)].events.set_data()
        except:
            self.viewer.add_image(images, name='Camera ' + str(cam), blending='additive', colormap=self.cmaps[cam], scale=(self.scaleX, self.scaleY))

        if self.autoscale == True:
            self.viewer.layers['Camera ' + str(cam)].contrast_limits=(0, numpy.amax(images))

    #  display_preprocess
    def _display_preprocess(self, images):
        """
        Update Napari viewer
        :param values: tuple
            camera numnber
            image to update
        :return None:
        """

        if self.method == 'downscale_mean':
            images = downscale_local_mean(images, (16,16))

        if self.method == 'decimate':
            images = images[0::16, 0::16]

        if self.method == 'downscale_max':
            N = 3
            for i in range(0,N):
                Itemp = numpy.zeros((4, int(images.shape[0]/2), int(images.shape[1]/2)), dtype = 'uint16')
                Itemp[0] = images[0::2,0::2]
                Itemp[1] = images[1::2,0::2]
                Itemp[2] = images[0::2,1::2]
                Itemp[3] = images[1::2,1::2]
                images = numpy.amax(Itemp, axis = 0, keepdims = False)

        if self.method == 'decimate_mean':
            images = 0.25*(images[0::2,0::2]+images[1::2,0::2]+images[0::2,1::2]+images[1::2,1::2]).astype('uint16')

        if self.method == 'corners':
            width = 800
            height = 450
            border = 10
            images_new = numpy.zeros((3*height,3*width), dtype = 'uint16')
            images_new[0:height,0:width] = images[0:height,0:width]
            images_new[height:2*height,0:width] = images[int(self.ROI_width_y/2-height/2):int(self.ROI_width_y/2+height/2),0:width]
            images_new[2*height:3*height,0:width] = images[self.ROI_width_y-height:self.ROI_width_y,0:width]
            images_new[0:height,width:2*width] = images[0:height,int(self.ROI_width_x/2-width/2):int(self.ROI_width_x/2+width/2)]
            images_new[height:2*height,width:2*width] = images[int(self.ROI_width_y/2-height/2):int(self.ROI_width_y/2+height/2),int(self.ROI_width_x/2-width/2):int(self.ROI_width_x/2+width/2)]
            images_new[2*height:3*height,width:2*width] = images[self.ROI_width_y-height:self.ROI_width_y,int(self.ROI_width_x/2-width/2):int(self.ROI_width_x/2+width/2)]
            images_new[0:height,2*width:3*width] = images[0:height,self.ROI_width_x-width:self.ROI_width_x]
            images_new[height:2*height,2*width:3*width] = images[int(self.ROI_width_y/2-height/2):int(self.ROI_width_y/2+height/2),self.ROI_width_x-width:self.ROI_width_x]
            images_new[2*height:3*height,2*width:3*width] = images[self.ROI_width_y-height:self.ROI_width_y,self.ROI_width_x-width:self.ROI_width_x]
            images_new[height-border:height,:] = 0
            images_new[2*height:2*height+border,:] = 0
            images_new[:,width-border:width] = 0
            images_new[:,2*width:2*width+border] = 0
            images = images_new

        if self.method == 'center':
            height = 2048
            width = 2048
            images = images[int(self.ROI_width_y/2-height/2):int(self.ROI_width_y/2+height/2), int(self.ROI_width_x/2-width/2):int(self.ROI_width_x/2+width/2)]

        if self.method == 'full':
            images = images

        return images

    @thread_worker
    def _acquire_live(self):

        yield 0, np.zeros((self.ROI_width_y, self.ROI_width_x), dtype = 'uint16')

    @thread_worker
    def _acquire_record(self):

        # TODO add these params into config
        n_tiles = 2
        n_frames = 20000 # frames
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

                    if frame_num % 4 == 0:
                        yield 0, image

                    # TODO flush this out. prototype code for monitoring ram buffer status and pausing if danger of dropping frames
                    # nq = grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET)
                    # if nq < int(ram_buffer): # pause acquisition if ram buffer is more than half full
                    #    daq.stop() # stop ao task which stops acquisition
                    #    while nq != ram_buffer: # wait for ram buffer to empty
                    #        nq = grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET)
                    #        print('Available buffer: ' + str(nq) + '/' + str(ram_buffer))
                    #        time.sleep(0.1)
                    #    daq.start() # restart once buffer is flushed       

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

    @magicgui(
        auto_call=True,
        live_display={"widget_type": "PushButton", "label": 'Live Display'},
        layout='horizontal'
    )
    def live_display(self, live_display=False):

        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False
            time.sleep(1.0/self.FrameRate)
            self.grabber.stop()
        else:
            if not(self.worker_live_started):
                self.worker_live_started=True
                self.worker_live_running=True
                self.grabber.start()
                self.worker_live.start()
            else:
                self.grabber.start()
                self.worker_live.resume()
                self.worker_live_running=True

    @magicgui(
        auto_call=True,
        record={"widget_type": "PushButton", "label": 'Record HDF5'},
        layout='horizontal'
    )
    def record(self, record=False):

        if self.worker_record_running:
            self.worker_record.pause()
            self.worker_record_running=False 
            time.sleep(1.0/(self.FrameRate))
            waveform_generator.stop()
            camera.stop()
        else:
            if not(self.worker_record_started):
                self.worker_record_started=True
                self.worker_record_running=True
                self.worker_record.start()
            else:
                self.worker_record.resume()
                self.worker_record_running=True
                camera.start()
                waveform_generator.start()
        if self.worker_live_running:
            self.worker_live.pause()
            self.worker_live_running=False