import numpy as np
from multiprocessing import Process, Value, Event
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
import tifffile

class MIPProcessor(Process):
    """Class for assembling 3 MIP images from raw images off the camera."""

    def __init__(self, shape, x_tile_num: int, y_tile_num: int, vol_x_voxels: int, vol_y_voxels: int, vol_z_voxels: int,
                 img_size_x_pixels: int, img_size_y_pixels: int,
                 img_pixel_dype: np.dtype, shm_name: str, file_dest: Path,
                 wavelength: int):
        """Init.
        :param shape: shape of shared memory buffer
        :param x_tile_num: current tile number in x dimension
        :param y_tile_num: current tile number in y dimension
        :param vol_z_voxels: size of the whole dataset z dimension in voxels
        :param img_size_x_pixels: size of a single image x dimension in pixels
        :param img_size_y_pixels:  size of a single image y dimension in pixels
        :param img_pixel_dype: image pixel data type
        :param shm_name: name of shared memory that we will interpret as a
            numpy array where the latest image is being written.
        :param file_dest: destination of the 3 MIP files.
        :param wavelength: wavelength of laser used to acquire images
        """
        super().__init__()
        self.more_images = Event()
        self.new_image = Event()
        self.is_busy = Event()
        self.more_images.clear()
        self.x_tile_num = x_tile_num
        self.y_tile_num = y_tile_num
        # Create XY, YZ, ZX placeholder images.
        self.mip_xy = np.zeros((img_size_x_pixels, img_size_y_pixels))  # dtype?
        self.mip_xz = np.zeros((vol_z_voxels, img_size_x_pixels))
        self.mip_yz = np.zeros((img_size_y_pixels, vol_z_voxels))

        # Pre-compute amount of shared memory to allocate (in bytes).
        self.shm = SharedMemory(shm_name)
        self.latest_imgs = np.ndarray(shape, img_pixel_dype,
                                     buffer=self.shm.buf)
        # These attributes are shared across processes.
        self.curr_tile_z = Value('d', 0)

        self.file_dest = file_dest
        self.wavelength = wavelength

    def run(self):
        # Setup connect to shared memory.
        while self.more_images.is_set():
            if self.new_image.is_set():
                self.is_busy.set()

                self.mip_xy = np.maximum(self.mip_xy, self.latest_imgs[self.curr_tile_z])

                self.mip_yz[:, self.curr_tile_z] = np.max(self.latest_imgs[self.curr_tile_z], axis=1)

                self.mip_xz[self.curr_tile_z, :] = np.max(self.latest_imgs[self.curr_tile_z], axis=0)

                self.is_busy.clear()
                self.shm.close()

            self.new_image.clear()

        tifffile.imwrite(self.file_dest/Path(f"mip_xy_tile_x_{self.self.x_tile_num:04}_y_{self.y_tile_num:04}_z_0000_ch_{self.wavelength}.tiff"), self.mip_xy)
        tifffile.imwrite(self.file_dest / Path(f"mip_yz_tile_x_{self.self.x_tile_num:04}_y_{self.y_tile_num:04}_z_0000_ch_{self.wavelength}.tiff"), self.mip_yz)
        tifffile.imwrite(self.file_dest / Path(f"mip_xz_tile_x_{self.self.x_tile_num:04}_y_{self.y_tile_num:04}_z_0000_ch_{self.wavelength}.tiff"), self.mip_xz)

    # Done MIPping! Cleanup. Process exits.
