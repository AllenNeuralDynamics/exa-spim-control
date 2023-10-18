import numpy as np
from multiprocessing import Process, Value, Event
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
import tifffile

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
        self.x_px = img_size_x_pixels
        self.y_px = img_size_y_pixels
        img_shape = (img_size_x_pixels, img_size_y_pixels)
        # Pre-compute amount of shared memory to allocate (in bytes).
        self.shm = SharedMemory(shm_name)
        self.latest_img = np.ndarray(img_shape, img_pixel_dype,
                                     buffer=self.shm.buf)
        # These attributes are shared across processes.
        self.curr_img_centroid_x = Value('d', 0)
        self.curr_img_centroid_y = Value('d', 0)
        self.curr_img_centroid_z = Value('d', 0)

        self.file_dest = file_dest

    def run(self):
        # Setup connect to shared memory.
        while self.more_images.is_set():
            self.is_busy.set()

            self.mip_xy[self.curr_img_centroid_x:self.curr_img_centroid_x+self.x_px,
                        self.curr_img_centroid_y:self.curr_img_centroid_y+self.y_px] = \
                np.maximum(self.mip_xy[self.curr_img_centroid_x:self.curr_img_centroid_x+self.x_px,
                        self.curr_img_centroid_y:self.curr_img_centroid_y+self.y_px], self.latest_img)

            self.mip_yz[self.curr_img_centroid_z, :] = np.max(self.latest_img, axis = 1)

            self.mip_xz[self.curr_img_centroid_z, :] = np.max(self.latest_img, axis=0)

            self.is_busy.clear()
            self.shm.close()

        tifffile.imwrite(self.file_dest/Path("mip_xy.tiff"), self.mip_xy)
        tifffile.imwrite(self.file_dest / Path("mip_yz.tiff"), self.mip_yz)
        tifffile.imwrite(self.file_dest / Path("mip_xz.tiff"), self.mip_xz)

    # Done MIPping! Cleanup. Process exits.
