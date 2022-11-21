#!/usr/bin/env python3

from math import floor, ceil
from multiprocessing import Process, Event, Array
from multiprocessing.shared_memory import SharedMemory
from ctypes import c_wchar
from PyImarisWriter import PyImarisWriter as pw
from time import sleep
import numpy as np
from datetime import datetime


class SharedDoubleBuffer:
    """A single-producer-single-consumer multi-process double buffer
    implemented as a numpy ndarray."""

    def __init__(self, shape: tuple, dtype: str):
        """

        :param shape: a tuple indicating the shape of the

        .. code-block: python

            dbl_buf = SharedDoubleBuffer((8, 320, 240), 'uint16')

            dbl_buf.write_mem[0][:,:] = np.zeros((320, 240), dtype='uint16')
            dbl_buf.write_mem[1][:,:] = np.zeros((320, 240), dtype='uint16')
            dbl_buf.write_mem[2][:,:] = np.zeros((320, 240), dtype='uint16')

            # When finished, switch buffers.
            # Note, user must apply flow control scheme to ensure another
            # process is done using the read_buf before we switch it.
            dbl_buf.toggle_buffers() # read_buf and write_buf have switched places.

        """
        nbytes = np.prod(shape)*np.dtype(dtype).itemsize
        self.mem_blocks = \
            [
                SharedMemory(create=True, size=nbytes),
                SharedMemory(create=True, size=nbytes)
            ]
        # Attach numpy array references to shared memory.
        self.read_buf = np.ndarray(shape, dtype=dtype,
                                   buffer=self.mem_blocks[0].buf)
        self.write_buf = np.ndarray(shape, dtype=dtype,
                                   buffer=self.mem_blocks[1].buf)
        # Attach references to the names of the memory locations.
        self.read_buf_mem_name = self.mem_blocks[0].name
        self.write_buf_mem_name = self.mem_blocks[1].name
        # Save values for querying later.
        self.dtype = dtype
        self.shape = shape
        self.nbytes = nbytes
        # Create flag to indicate if data has been read out from the read buf.
        self.is_read = Event()
        self.is_read.clear()

    def toggle_buffers(self):
        # Toggle who acts as read buf and write buf.
        tmp = self.read_buf
        self.read_buf = self.write_buf
        self.write_buf = tmp
        # Do the same thing with the shared memory location names
        tmp = self.read_buf_mem_name
        self.read_buf_mem_name = self.write_buf_mem_name
        self.write_buf_mem_name = tmp

    def close_and_unlink(self):
        for mem in self.mem_blocks:
            mem.close()
            mem.unlink()


class DataWriter(Process):

    def __init__(self, test_config, mem_shape, mem_dtype, mem_nbytes,
                 num_frames, frame_chunk_size):
        super().__init__()
        # members for executing job
        self.test_config = test_config
        self.num_frames = num_frames
        self.frame_chunk_size = frame_chunk_size
        self.callback_class = MyCallbackClass(self.pid)
        # data for reconstructing the buffer.
        self._shm_name = Array(c_wchar, 32)  # hidden and exposed via property.
        self.mem_shape = mem_shape
        self.mem_dtype = mem_dtype
        self.mem_nbytes = mem_nbytes
        # Flow Control:
        self.done_reading = Event()
        self.done_reading.set()

    @property
    def shm_name(self):
        """Convenience getter to extract the string from the c array."""
        return str(self._shm_name[:]).split('\x00')[0]

    @shm_name.setter
    def shm_name(self, name: str):
        """Convenience setter to set the string value within the c array."""
        for i, c in enumerate(name):
            self._shm_name[i] = c
        self._shm_name[len(name)] = '\x00'  # Null terminate the string.

    def run(self):
        # Imaris file setup.
        image_size = pw.ImageSize(x=self.mem_shape[0], y=self.mem_shape[1], z=self.num_frames, c=1, t=1)
        dimension_sequence = pw.DimensionSequence('x', 'y', 'z', 'c', 't')
        #block_size = image_size
        block_size = pw.ImageSize(x=self.mem_shape[0], y=self.mem_shape[1], z=self.frame_chunk_size, c=1, t=1)
        sample_size = pw.ImageSize(x=1, y=1, z=1, c=1, t=1)
        output_filename = f'PyImarisWriterNumpyExample{self.test_config.mId}.ims'
        options = pw.Options()
        # TODO: enable options here.
        options.mNumberOfThreads = 32#12
        options.mCompressionAlgorithmType = pw.eCompressionAlgorithmShuffleLZ4#pw.eCompressionAlgorithmGzipLevel2
        options.mEnableLogProgress = True
        # Create a converter.
        application_name = 'PyImarisWriter'
        application_version = '1.0.0'
        converter = pw.ImageConverter(self.test_config.mImaris_type, image_size, sample_size, dimension_sequence, block_size,
                                      output_filename, options, application_name, application_version, self.callback_class)

        # Data Collection Loop.
        #  Wait on a new data chunk. Dispatch it to ImarisWriter
        num_blocks = ceil(self.num_frames / self.frame_chunk_size)
        last_chunk_size = self.num_frames % self.frame_chunk_size
        last_chunk_index = num_blocks-1
        for chunk_index in range(num_blocks):
            # Wait for new data.
            print("  Waiting for new data.")
            while self.done_reading.is_set():
                sleep(0.001)
            print(f"  Processing chunk {chunk_index} data.")
            buf_mem = SharedMemory(self.shm_name, size=self.mem_nbytes)
            frames = np.ndarray(self.mem_shape, self.mem_dtype,
                                  buffer=buf_mem.buf)
            # Process incoming data.
            #chunk_size = self.frame_chunk_size if chunk_index != last_chunk_index else last_chunk_size
            block_index = pw.ImageSize(x=0, y=0, z=chunk_index, c=0, t=0)
            converter.CopyBlock(frames, block_index)
            # Cleanup this block.
            buf_mem.close()
            print(f"  Wrote chunk {chunk_index}.")
            self.done_reading.set()

        adjust_color_range = True
        image_extents = pw.ImageExtents(0, 0, 0, image_size.x, image_size.y, image_size.z)
        parameters = pw.Parameters()
        parameters.set_value('Image', 'ImageSizeInMB', 2400)
        parameters.set_value('Image', 'Info', self.test_config.mTitle)
        parameters.set_channel_name(0, 'My Channel 1')
        time_infos = [datetime.today()]
        color_infos = [pw.ColorInfo() for _ in range(image_size.c)]
        color_infos[0].set_color_table(self.test_config.mColor_table)

        converter.Finish(image_extents, parameters, time_infos, color_infos, adjust_color_range)

        converter.Destroy()
        print('Wrote {} to {}'.format(self.test_config.mTitle, output_filename))


if __name__ == "__main__":

    # Script Level Settings
    cols = 320#14192#320
    rows = 240#10640#240
    frame_count = 32
    chunk_size = 4

    configurations = get_test_configurations()
    try:
        ps_buffers = [SharedDoubleBuffer((cols, rows, chunk_size), np.uint16) for i in configurations]
        ps_workers = [DataWriter(cfg, ps.shape, ps.dtype, ps.nbytes, frame_count, chunk_size) for cfg, ps in zip(configurations, ps_buffers)]
        print(f"Starting {len(ps_workers)} workers.")
        for ps_worker in ps_workers:
            ps_worker.start()
        print(f"Producing data.")
        for frame_index in range(frame_count):
            chunk_num = floor(frame_index / chunk_size)
            chunk_index = frame_index % chunk_size
            print(f"frame: {frame_index} | chunk_num: {chunk_num} | chunk_index: {chunk_index}")
            # Write some data into each buffer
            for ps_buffer in ps_buffers:
                ps_buffer.write_buf[chunk_index][:,:] = chunk_index  # dummy value
            # Dispatch chunk if it is full
            if chunk_index == chunk_size - 1:  # chunk is full.
                for ps_buffer, ps_worker in zip(ps_buffers, ps_workers):
                    ps_buffer.toggle_buffers()
                    # Send over the read buffer shm name.
                    ps_worker.shm_name = ps_buffer.read_buf_mem_name
                    ps_worker.done_reading.clear()
                # TODO: we can handle this more elegantly.
                for ps_worker in ps_workers:
                    print("Waiting for process to handle new data.")
                    ps_worker.done_reading.wait()
    finally:
        # kill the process? TODO
        #data_writer_worker.terminate()
        # Release shared memory.
        print("Joining processes")
        for ps_worker in ps_workers:
            ps_worker.join()
        print("Unlinking shared memory.")
        for ps_buffer in ps_buffers:
            ps_buffer.close_and_unlink()
