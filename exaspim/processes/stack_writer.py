import numpy as np
from exaspim.data_structures.shared_double_buffer import SharedDoubleBuffer
from multiprocessing import Process, Array, Event
from multiprocessing.shared_memory import SharedMemory
from ctypes import c_wchar
from PyImarisWriter import PyImarisWriter as pw
from pathlib import Path
from datetime import datetime
from matplotlib.colors import hex2color
from time import sleep
from math import floor, ceil


class ImarisProgressChecker(pw.CallbackClass):
    """Class for tracking progress of an active ImarisWriter disk-writing
    operation."""

    def __init__(self, stack_name):
        self.stack_name = stack_name
        self.mUserDataProgress = 0
        self.progress = 0  # a float representing the progress.

    def RecordProgress(self, progress, total_bytes_written):
        self.progress = progress
        progress100 = int(progress * 100)
        if progress100 - self.mUserDataProgress >= 25:
            self.mUserDataProgress = progress100
            print(f"{self.mUserDataProgress}% Complete; "
                  f"{total_bytes_written/1.0e9:.3f} GB written for "
                  f"{self.stack_name}.ims.")


class StackWriter(Process):
    """Class for writing a stack of frames to a file on disk."""

    def __init__(self, image_rows: int, image_columns: int, image_count: int,
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
        super().__init__()
        # metadata to create the file.
        self.cols = image_columns
        self.rows = image_rows
        self.img_count = image_count
        self.first_img_centroid_x_um = first_img_centroid_x
        self.first_img_centroid_y_um = first_img_centroid_y
        self.pixel_x_size_um = pixel_x_size_um
        self.pixel_y_size_um = pixel_y_size_um
        self.pixel_z_size_um = pixel_z_size_um
        # metatdata to write to the file before closing it.
        self.channel_name = channel_name
        self.chunk_size = chunk_size
        self.thread_count = thread_count
        self.compression_style = compression_style
        self.dtype = datatype
        self.dest_path = dest_path
        self.stack_name = stack_name
        self.hex_color = viz_color_hex
        self.converter = None
        # Specs for reconstructing the shared memory object.
        self._shm_name = Array(c_wchar, 32)  # hidden and exposed via property.
        self.shm_shape = (self.cols, self.rows, self.chunk_size)
        self.shm_nbytes = int(np.prod(self.shm_shape, dtype=np.int64)*np.dtype(self.dtype).itemsize)
        self.frames = None  # will be replaced with an ndarray from shared mem.
        # Flow control attributes to synchronize inter-process communication.
        self.done_reading = Event()
        self.done_reading.set()  # Set after processing all data in shared mem.
        # Internal flow control attributes to monitor compression progress.
        self.callback_class = ImarisProgressChecker(self.stack_name)

    @property
    def shm_name(self):
        """Convenience getter to extract the shared memory address (string)
        from the c array."""
        return str(self._shm_name[:]).split('\x00')[0]

    @shm_name.setter
    def shm_name(self, name: str):
        """Convenience setter to set the string value within the c array."""
        for i, c in enumerate(name):
            self._shm_name[i] = c
        self._shm_name[len(name)] = '\x00'  # Null terminate the string.

    def run(self):
        image_size = pw.ImageSize(x=self.cols, y=self.rows, z=self.img_count, c=1, t=1)
        dimension_sequence = pw.DimensionSequence('x', 'y', 'z', 'c', 't')
        block_size = pw.ImageSize(x=self.cols, y=self.rows, z=self.chunk_size, c=1, t=1)
        sample_size = pw.ImageSize(x=1, y=1, z=1, c=1, t=1)
        # Create Options object.
        opts = pw.Options()
        opts.mNumberOfThreads = self.thread_count
        opts.mEnableLogProgress = True
        # compression options are limited.
        if self.compression_style == 'lz4':
            opts.mCompressionAlgorithmType = pw.eCompressionAlgorithmShuffleLZ4
        elif self.compression_style.upper() == 'None':
            opts.mCompressionAlgorithmType = pw.eCompressionAlgorithmNone

        application_name = 'PyImarisWriter'
        application_version = '1.0.0'

        filepath = str((self.dest_path / Path(f"{self.stack_name}.ims")).absolute())
        self.converter = \
            pw.ImageConverter(self.dtype, image_size, sample_size, dimension_sequence, block_size,
                              filepath, opts, application_name, application_version, self.callback_class)

        # Write some dummy data to file.
        chunk_count = ceil(self.img_count/self.chunk_size)
        last_chunk_size = self.img_count % self.chunk_size
        last_chunk = chunk_count - 1
        for chunk_num in range(chunk_count):
            block_index = pw.ImageSize(x=0, y=0, z=chunk_num, c=0, t=0)
            # Wait for new data.
            while self.done_reading.is_set():
                sleep(0.001)
            # Attach a reference to the data from shared memory.
            shm = SharedMemory(self.shm_name, size=self.shm_nbytes)
            frames = np.ndarray(self.shm_shape, self.dtype, buffer=shm.buf)
            print(f"Ch{self.channel_name} writing chunk "
                  f"{chunk_num+1}/{chunk_count} of size {frames.shape}.")
            # TODO: do we need this?
            #self.converter.CopyBlock(np.transpose(frames, (2, 1, 0)), block_index)
            self.converter.CopyBlock(frames, block_index)
            shm.close()
            self.done_reading.set()
#        self.close()
#
#    def close(self):
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

        # Wait for file writing to finish.
        if self.callback_class.progress < 1.0:
            print(f"Waiting for Data writing to complete for "
                  f"channel {self.channel_name}[nm] channel."
                  f"Progress is {self.callback_class.progress:.3f}.")
        while self.callback_class.progress < 1.0:
            sleep(1.0)
            print(f"Waiting for Data writing to complete for "
                  f"channel {self.channel_name}[nm] channel."
                  f"Progress is {self.callback_class.progress:.3f}.")

        print("Writing image extents and closing file.")
        image_extents = pw.ImageExtents(-x0, -y0, -z0, -xf, -yf, -zf)
        adjust_color_range = False
        parameters = pw.Parameters()
        parameters.set_channel_name(0, self.channel_name)
        time_infos = [datetime.today()]
        color_infos = [pw.ColorInfo()]
        color_spec = pw.Color(*(*hex2color(self.hex_color), 1.0))
        color_infos[0].set_base_color(color_spec)
        # color_infos[0].set_range(0,200)  # possible to autoexpose through this cmd.

        self.converter.Finish(image_extents, parameters, time_infos,
                              color_infos, adjust_color_range)
        self.converter.Destroy()

