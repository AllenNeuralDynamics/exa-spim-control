import numpy as np
from multiprocessing import Process, Value, Event, Array
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
import tifffile
import array

class MIPProcessor(Process):
    """Class for assembling 3 MIP images from raw images off the camera."""

    def __init__(self, x_tile_num: int, y_tile_num: int, vol_z_voxels: int,
                 img_size_x_pixels: int, img_size_y_pixels: int,
                 img_pixel_dtype: np.dtype, shm_name: str, file_dest: Path,
                 wavelength: int):
        """Init.
        :param x_tile_num: current tile number in x dimension
        :param y_tile_num: current tile number in y dimension
        :param vol_z_voxels: size of the whole dataset z dimension in voxels
        :param img_size_x_pixels: size of a single image x dimension in pixels
        :param img_size_y_pixels:  size of a single image y dimension in pixels
        :param img_pixel_dtype: image pixel data type
        :param shm_name: name of shared memory that we will interpret as a
            numpy array where the latest image is being written.
        :param file_dest: destination of the 3 MIP files.
        :param wavelength: wavelength of laser used to acquire images
        """
        super().__init__()
        self.more_images = Event()
        self.new_image = Event()
        self.is_busy = Event()
        self.new_image.clear()
        self.is_busy.clear()
        self.more_images.clear()
        self.x_tile_num = x_tile_num
        self.y_tile_num = y_tile_num
        self.shm_shape = (img_size_x_pixels, img_size_y_pixels)
        self.dtype = img_pixel_dtype
        # Create XY, YZ, ZX placeholder images.
        self.mip_xy = np.zeros((img_size_x_pixels, img_size_y_pixels))  # dtype?
        self.mip_xz = np.zeros((vol_z_voxels, img_size_x_pixels))
        self.mip_yz = np.zeros((img_size_y_pixels, vol_z_voxels))

        # Create attributes to open shared memory in run function
        self.shm = SharedMemory(shm_name, create=False)
        self.latest_img = np.ndarray(self.shm_shape, self.dtype, buffer=self.shm.buf)

        self.file_dest = file_dest
        self.wavelength = wavelength

    def run(self):
        frame_index = 0
        # Build mips. Assume frames increment sequentially in z.

        while self.more_images.is_set():
            if self.new_image.is_set():
                self.is_busy.set()
                self.latest_img = np.ndarray(self.shm_shape, self.dtype, buffer=self.shm.buf)
                self.mip_xy = np.maximum(self.mip_xy, self.latest_img)
                self.mip_yz[:, frame_index] = np.max(self.latest_img, axis=0)
                self.mip_xz[frame_index, :] = np.max(self.latest_img, axis=1)
                self.is_busy.clear()
                frame_index += 1
            self.new_image.clear()

        tifffile.imwrite(self.file_dest/Path(f"mip_xy_tile_x_{self.x_tile_num:04}_y_{self.y_tile_num:04}_z_0000_ch_{self.wavelength}.tiff"), self.mip_xy)
        tifffile.imwrite(self.file_dest / Path(f"mip_yz_tile_x_{self.x_tile_num:04}_y_{self.y_tile_num:04}_z_0000_ch_{self.wavelength}.tiff"), self.mip_yz)
        tifffile.imwrite(self.file_dest / Path(f"mip_xz_tile_x_{self.x_tile_num:04}_y_{self.y_tile_num:04}_z_0000_ch_{self.wavelength}.tiff"), self.mip_xz)

    # Done MIPping! Cleanup. Process exits.
