from multiprocessing import Process, Event, Array
from multiprocessing.shared_memory import SharedMemory
import numpy as np


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
        # Overflow errors without casting for sufficiently larg datasets
        nbytes = int(np.prod(shape, dtype=np.int64)*np.dtype(dtype).itemsize)
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
        """Switch read and write references and the locations of their shared
        memory."""
        # Toggle who acts as read buf and write buf.
        tmp = self.read_buf
        self.read_buf = self.write_buf
        self.write_buf = tmp
        # Do the same thing with the shared memory location names
        tmp = self.read_buf_mem_name
        self.read_buf_mem_name = self.write_buf_mem_name
        self.write_buf_mem_name = tmp

    def close_and_unlink(self):
        """Shared memory cleanup; call when done using this object."""
        for mem in self.mem_blocks:
            mem.close()
            mem.unlink()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup called automatically if opened using a `with` statement."""
        self.close_and_unlink()
