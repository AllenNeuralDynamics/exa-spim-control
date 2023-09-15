import numpy as np
from multiprocessing import Process, Value, Event
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path


class MIPProcessor(Process):
    """Class for assembling 3 MIP images from raw images off the camera."""

    def __init__(self, vol_x_voxels: int, vol_y_voxels: int, vol_z_voxels: int,
                 img_size_x_pixels: int, img_size_y_pixels: int,
                 img_pixel_dype: np.dtype, shm_name: str, file_dest: Path):
        """Init.
        :param vol_x_voxels: size of the whole dataset x dimension in voxels
        :param vol_y_voxels: size of the whole dataset y dimension in voxels
        :param vol_z_voxels: size of the whole dataset z dimension in voxels
        :param img_size_x_pixels: size of a single image x dimension in pixels
        :param img_size_y_pixels:  size of a single image y dimension in pixels
        :param img_pixel_dype: image pixel data type
        :param shm_name: name of shared memory that we will interpret as a
            numpy array where the latest image is being written.
        :param file_dest: destination of the 3 MIP files.
        """
        super().__init__()
        self.more_images = Event()
        self.is_busy = Event()
        self.more_images.clear()
        # Create XY, YZ, ZX placeholder images.
        self.mip_xy = np.zeros((vol_x_voxels, vol_y_voxels))  # dtype?
        self.mip_xz = np.zeros((vol_x_voxels, vol_z_voxels))
        self.mip_yz = np.zeros((vol_y_voxels, vol_z_voxels))
        img_shape = (img_size_x_pixels, img_size_y_pixels)
        # Pre-compute amount of shared memory to allocate (in bytes).
        self.shm = SharedMemory(shm_name)
        self.latest_img = np.ndarray(img_shape, img_pixel_dype,
                                     buffer=self.shm.buf)
        # These attributes are shared across processes.
        self.curr_img_centroid_x = Value('d', 0)
        self.curr_img_centroid_y = Value('d', 0)

    def run(self):
        # Setup connect to shared memory.
        while self.more_images.is_set():
            self.is_busy.set()
            # Get the position where this image was taken.
            # Apply MIP at the specified location in each image.
            # MIP XY
            #self.np.max(self.mip_xy[subset??], self.latest_img)
            # MIP YZ
            # First mip image into a line. Then into the mosaic.
            # MIP ZX
            # First mip image into a line. Then into the mosaic.
            # Flag that we are not busy.
            # exit if no more images.
            self.is_busy.clear()
            self.shm.close()
    # Done MIPping! Cleanup. Process exits.
