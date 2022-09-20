import threading
import numpy
from PyImarisWriter import PyImarisWriter as pw
from pathlib import Path
from datetime import datetime
from matplotlib.colors import hex2color


class MyCallbackClass(pw.CallbackClass):

    def __init__(self):
        self.mUserDataProgress = 0

    def RecordProgress(self, progress, total_bytes_written):
        progress100 = int(progress * 100)
        if progress100 - self.mUserDataProgress >= 10:
            self.mUserDataProgress = progress100
            print('{}% Complete: {} GB written'.format(self.mUserDataProgress, total_bytes_written / 1.0e9))


class StackWriter:
    """Class for writing a stack of frames to a file on disk."""

    def __init__(self):
        self.threads = []
        self.converter = None
        self.callback_class = None

        self.rows = None
        self.cols = None
        self.img_count = None
        self.hex_color = "#FFFFFF"
        self.channel_name = None

    # def configure(self, cfg, stack_name):
    def configure(self, image_rows: int, image_columns: int, image_count: int,
                  first_img_centroid_x: float, first_img_centroid_y: float,
                  chunk_size: int, thread_count: int, compression_style: str,
                  datatype: str, dest_path: Path, stack_name: str,
                  channel_name: str, viz_color_hex: str):
        """Setup the StackWriter according to the config.

        :param image_rows: image sensor rows.
        :param image_columns: image sensor columns.
        :param image_count: number of images in a stack.
        :param first_img_centroid_x: x centroid of the first tile.
        :param first_img_centroid_y: y centroid of the first tile.
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

        self.callback_class = MyCallbackClass()
        filepath = str((dest_path / Path(f"{stack_name}.ims")).absolute())
        self.converter = \
            pw.ImageConverter(datatype, image_size, sample_size,
                              dimension_sequence, block_size, filepath,
                              opts, application_name, application_version,
                              self.callback_class)
        # metatdata to write to the file before closing it.
        self.channel_name = channel_name
        self.hex_color = viz_color_hex

    def write_block(self, data, chunk_num):
        thread = threading.Thread(target=self.write_block_worker,
                                  args=(numpy.transpose(data, (2, 1, 0)),
                                        chunk_num))
        thread.start()
        self.threads.append(thread)

    def close(self):

        # TODO: refactor to take no options upon closing.
        for thread in self.threads:
            if thread.is_alive():
                thread.join()
        adjust_color_range = False
        # Compute the start/end extremes of the enclosed rectangular solid.
        # (x0, y0, z0) position (in [um]) of the beginning of the first voxel,
        # (xf, yf, zf) position (in [um]) of the end of the last voxel.
        # TODO: figure out a good way to handle this.
        x0 = self.cols * self.cfg.pixel_x * (y_tile) * (1 - self.cfg.y_overlap / 100)
        y0 = self.rows * self.cfg.pixel_y * (z_tile) * (1 - self.cfg.z_overlap / 100)
        z0 = 0
        xf = x0 + self.cfg.cam_x * self.cfg.pixel_x
        yf = y0 + self.cfg.cam_y * self.cfg.pixel_y
        zf = z0 + self.cfg.n_frames * self.cfg.pixel_z
        image_extents = pw.ImageExtents(-x0, -y0, -z0, -xf, -yf, -zf)
        parameters = pw.Parameters()
        parameters.set_channel_name(0, self.channel_name)
        time_infos = [datetime.today()]
        color_infos = [pw.ColorInfo()]
        color_spec = pw.Color((*hex2color(self.hex_color), 1.0))
        color_infos[0].set_base_color(color_spec)
        # color_infos[0].set_range(0,200)  # possible to autoexpose through this cmd.
        self.converter.Finish(image_extents, parameters, time_infos,
                              color_infos, adjust_color_range)
        self.converter.Destroy()

    def write_block_worker(self, data, chunk_num):
        self.converter.CopyBlock(data, pw.ImageSize(x=0, y=0, z=chunk_num,
                                                    c=0, t=0))
