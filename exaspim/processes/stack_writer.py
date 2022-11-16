import logging
import numpy
from threading import Thread, Lock
from PyImarisWriter import PyImarisWriter as pw
from pathlib import Path
from datetime import datetime
from matplotlib.colors import hex2color
from time import sleep


class ImarisProgressChecker(pw.CallbackClass):

    def __init__(self, stack_name):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.stack_name = stack_name
        self.mUserDataProgress = 0

        self.progress = 0  # a float representing the progress.

    def RecordProgress(self, progress, total_bytes_written):
        self.progress = progress
        progress100 = int(progress * 100)
        if progress100 - self.mUserDataProgress >= 10:
            self.mUserDataProgress = progress100
            self.log.debug(f"{self.mUserDataProgress}% Complete; "
                           f"{total_bytes_written/1.0e9:.3f} GB written for "
                           f"{self.stack_name}.ims.")


class StackWriter:
    """Class for writing a stack of frames to a file on disk."""

    #lock = Lock()

    def __init__(self):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.threads = []
        self.converter = None
        self.callback_class = None

        self.rows = None
        self.cols = None
        self.img_count = None
        self.hex_color = "#FFFFFF"
        self.channel_name = None

        self.pixel_x_size_um = None
        self.pixel_y_size_um = None
        self.pixel_z_size_um = None
        self.first_img_centroid_x_um = None
        self.first_img_centroid_y_um = None

    # def configure(self, cfg, stack_name):
    def configure(self, image_rows: int, image_columns: int, image_count: int,
                  first_img_centroid_x: float, first_img_centroid_y: float,
                  pixel_x_size_um: float, pixel_y_size_um: float,
                  pixel_z_size_um: float,
                  chunk_size: int, thread_count: int, compression_style: str,
                  datatype: str, dest_path: Path, stack_name: str,
                  channel_name: str, viz_color_hex: str):
        """Setup the StackWriter according to the config.

        :param image_rows: image sensor rows.
        :param image_columns: image sensor columns.
        :param image_count: number of images in a stack.
        :param first_img_centroid_x: x centroid of the first tile.
        :param first_img_centroid_y: y centroid of the first tile.
        :param pixel_x_size_um:
        :param pixel_y_size_um:
        :param pixel_z_size_um:
        :param chunk_size: size of the chunk.
        :param thread_count: number of threads to split this operation across.
        :param compression_style: compression algorithm to use on the images.
        :param datatype: string representation of the image datatype.
        :param dest_path: the filepath to write the image stack to.
        :param stack_name: file name without the .ims extension.
        :param channel_name: name of the channel as it appears in the file.
        :param viz_color_hex: color (as a hex string) for the file signal data.
        """

        self.rows = image_rows
        self.cols = image_columns
        self.img_count = image_count
        self.pixel_x_size_um = pixel_x_size_um
        self.pixel_y_size_um = pixel_y_size_um
        self.pixel_z_size_um = pixel_z_size_um
        self.first_img_centroid_x_um = first_img_centroid_x
        self.first_img_centroid_y_um = first_img_centroid_y
        # metatdata to write to the file before closing it.
        self.channel_name = channel_name
        self.hex_color = viz_color_hex

        #while self.__class__.lock.locked():
        #    self.log.warning(f"Ch{self.channel_name} waiting to get lock to close file..")
        #    sleep(1.0)
        #with self.__class__.lock:
        # image_size=pw.ImageSize(x=self.cfg.cam_x, y=self.cfg.cam_y, z=self.cfg.n_frames, c=1, t=1)
        image_size = pw.ImageSize(x=self.cols, y=self.rows, z=self.img_count,
                                  c=1, t=1)
        # This can be changed. This might affect how we open the imaris file.
        dimension_sequence = pw.DimensionSequence('x', 'y', 'z', 'c', 't')
        # block_size=pw.ImageSize(x=self.cfg.cam_x, y=self.cfg.cam_y,
        block_size = pw.ImageSize(x=self.cols, y=self.rows, z=chunk_size,
                                  c=1, t=1)
        sample_size = pw.ImageSize(x=1, y=1, z=1, c=1, t=1)
        # Create Options object.
        opts = pw.Options()
        opts.mNumberOfThreads = thread_count
        # compression options are limited.
        if compression_style == 'lz4':
            opts.mCompressionAlgorithmType = pw.eCompressionAlgorithmShuffleLZ4
        elif compression_style == 'none':
            opts.mCompressionAlgorithmType = pw.eCompressionAlgorithmNone
        # TODO: log what we actually used and whether we didn't specify one.
        opts.mEnableLogProgress = True

        application_name = 'PyImarisWriter'
        application_version = '1.0.0'

        self.callback_class = ImarisProgressChecker(stack_name)
        filepath = str((dest_path / Path(f"{stack_name}.ims")).absolute())

        self.converter = \
            pw.ImageConverter(datatype, image_size, sample_size,
                              dimension_sequence, block_size, filepath,
                              opts, application_name, application_version,
                              self.callback_class)

    def write_block(self, data, chunk_num):
        name = f"chunk_{chunk_num}_ch{self.channel_name}_writer"
        self.log.debug(f"Creating {name} thread.")
        thread = Thread(target=self.write_block_worker,
                        name=f"chunk_{chunk_num}_ch{self.channel_name}_writer",
                        args=(numpy.transpose(data, (2, 1, 0)), chunk_num))
        self.threads.append(thread)
        self.threads[-1].start()

    def close(self):
        # Wait for all blocks to be copied.
        self.log.debug(f"Joining Ch{self.channel_name} remaining threads.")
        for thread in self.threads:
            self.log.debug(f"Joining {thread.name}")
            thread.join()
        adjust_color_range = False
        # Compute the start/end extremes of the enclosed rectangular solid.
        # (x0, y0, z0) position (in [um]) of the beginning of the first voxel,
        # (xf, yf, zf) position (in [um]) of the end of the last voxel.

        #x0 = self.cols * self.pixel_x_size_um * (y_tile) * (1 - self.cfg.y_overlap / 100)
        #y0 = self.rows * self.pixel_y_size_um * (z_tile) * (1 - self.cfg.z_overlap / 100)
        x0 = self.first_img_centroid_x_um - (self.pixel_x_size_um * 0.5 * self.cols)
        y0 = self.first_img_centroid_x_um - (self.pixel_y_size_um * 0.5 * self.rows)
        z0 = 0
        #xf = x0 + self.cfg.cam_x * self.cfg.pixel_x
        #yf = y0 + self.cfg.cam_y * self.cfg.pixel_y
        #zf = z0 + self.cfg.n_frames * self.cfg.pixel_z
        xf = self.first_img_centroid_x_um + (self.pixel_x_size_um * 0.5 * self.cols)
        yf = self.first_img_centroid_y_um + (self.pixel_y_size_um * 0.5 * self.rows)
        zf = z0 + self.img_count * self.pixel_z_size_um
        #while self.__class__.lock.locked():
        #    self.log.warning(f"Ch{self.channel_name} waiting to get lock to close file..")
        #    sleep(0.001)
        #with self.__class__.lock:

        # Wait for file writing to finish.
        if self.callback_class.progress < 1.0:
            self.log.debug(f"Waiting for Data writing to complete for "
                           f"channel {self.channel_name}[nm] channel."
                           f"Progress is {self.callback_class.progress:.3f}.")
        while self.callback_class.progress < 1.0:
            sleep(0.001)

        self.log.debug("Writing metadata to tile stack. First Tile: "
                       f"({round(x0)}, {round(y0)}, {round(z0)})[um]. "
                       f"Last Tile: ({round(xf)}, {round(yf)}, {round(zf)})[um].")
        image_extents = pw.ImageExtents(-x0, -y0, -z0, -xf, -yf, -zf)
        parameters = pw.Parameters()
        parameters.set_channel_name(0, self.channel_name)
        time_infos = [datetime.today()]
        color_infos = [pw.ColorInfo()]
        color_spec = pw.Color(*(*hex2color(self.hex_color), 1.0))
        color_infos[0].set_base_color(color_spec)
        # color_infos[0].set_range(0,200)  # possible to autoexpose through this cmd.

        self.log.debug("Finishing image extents.")
        self.converter.Finish(image_extents, parameters, time_infos,
                              color_infos, adjust_color_range)
        self.log.debug("Destroying converter.")
        self.converter.Destroy()
        self.log.debug("Converter destroyed.")
        self.log.debug(f"Data writing for {self.channel_name}[mm] channel is complete.")

    def write_block_worker(self, data, chunk_num):
        #while self.__class__.lock.locked():
        #    #self.log.warning(f"Ch{self.channel_name} Chunk {chunk_num} thread waiting to get lock.")
        #    sleep(0.001)
        #with self.__class__.lock:
        #    self.log.warning(f"Ch{self.channel_name} Chunk {chunk_num} got the lock.")
        self.log.debug(f"Dispatching chunk {chunk_num} block to compressor for {self.channel_name}[nm] channel.")
        self.converter.CopyBlock(data, pw.ImageSize(x=0, y=0, z=chunk_num,
                                                    c=0, t=0))
        self.log.debug(f"Done dispatching chunk {chunk_num} block to compressor for {self.channel_name}[nm] channel.")
        # Image writing does not start until all threads have been started?
