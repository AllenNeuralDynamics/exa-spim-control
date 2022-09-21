"""Abstraction of the ExaSPIM Instrument."""

import numpy as np
from math import ceil
from pathlib import Path
from psutil import virtual_memory
from time import perf_counter
from mock import NonCallableMock as Mock
from exaspim.exaspim_config import ExaspimConfig
from exaspim.devices.camera import Camera
from exaspim.processes.mip_processor import MIPProcessor
from exaspim.processes.stack_writer import StackWriter
from exaspim.processes.file_transfer import FileTransfer
from exaspim.processes.data_logger import DataLogger
from tigerasi.tiger_controller import TigerController, UM_TO_STEPS
from tigerasi.sim_tiger_controller import TigerController as SimTiger
# TODO: consolodate these later.
from mesospim.spim_base import Spim
from mesospim.devices.tiger_components import SamplePose


class Exaspim(Spim):

    def __init__(self, config_filepath: str, log_filename: str = 'debug.log',
                 console_output: bool = True,
                 color_console_output: bool = False,
                 console_output_level: str = 'info', simulated: bool = False):

        super().__init__(config_filepath, log_filename, console_output,
                         color_console_output, console_output_level, simulated)
        self.cfg = ExaspimConfig(config_filepath)

        # Separate Processes. Note: most of these are per-channel.
        self.data_logger_worker = None  # External Memento data logger.
        # TODO: make stack_writer its own process.
        self.stack_writer_worker = []  # writes img chunks to a stack on disk
        self.mip_worker = []  # aggregates MIPs from frames
        self.stack_transfer_worker = []  # writes stacks on disk to the cloud

        # Hardware
        self.cam = Camera() if not self.simulated else Mock(Camera)
        self.ni = None #WaveformGenerator()
        self.etl = None
        self.gavlo_a = None
        self.gavlo_b = None
        self.daq = None
        self.tigerbox = TigerController(**self.cfg.tiger_obj_kwds) if not \
            self.simulated else SimTiger(**self.cfg.tiger_obj_kwds)
        self.sample_pose = SamplePose(self.tigerbox,
                                      **self.cfg.sample_pose_kwds)

        # Extra Internal State attributes for the current image capture
        # sequence. These really only need to persist for logging purposes.
        self.image_index = 0  # current image to capture.
        self.total_tiles = 0  # tiles to be captured.
        self.stage_x_pos = None
        self.stage_y_pos = None

        # TODO: consider SharedMemory double buffer for working with MIPS
        #   and Imaris Writer data compressor in another process.
        # TODO: do the minimum (ideally zero) number of image transformations
        #   before handing them off to Imaris Writer.

        # Setup hardware according to the config.
        self._setup_motion_stage()
        self._setup_camera()

    def _setup_motion_stage(self):
        """Configure the sample stage according to the config."""
        # The tigerbox x axis is the sample pose z axis.
        #   TODO: map this in the config.
        self.tigerbox.set_axis_backlash(x=0)

    def _setup_camera(self):
        """Configure the camera according to the config."""
        # pass config parameters into object here.
        pass

    def setup_imaging_hardware(self):
        """provision the daq according to the dataset we are going to collect."""
        pass

    def check_system_memory_resources(self, channel_count: int,
                                      mem_chunk: int):
        """Make sure this machine can image under the specified configuration.

        :param channel_count: the number of channels we want to image with.
        :raises MemoryError:
        """
        # Check memory. Can we even allocate enough ram for all the specified
        #   channels?
        bytes_per_gig = (1024**3)
        used_mem_gigabytes = \
            (self.cfg.bytes_per_image * mem_chunk) \
            / bytes_per_gig * channel_count
        free_mem_gigabytes = virtual_memory()[1] / bytes_per_gig
        if free_mem_gigabytes < used_mem_gigabytes:
            raise MemoryError("System does not have enough memory to run "
                              "the specified number of channels. "
                              f"{used_mem_gigabytes:.1f}[GB] are required but "
                              f"{free_mem_gigabytes:.1f}[GB] are available.")

    def run_from_config(self):
        self.collect_volumetric_image(self.cfg.volume_x_um,
                                      self.cfg.volume_y_um,
                                      self.cfg.volume_z_um,
                                      self.cfg.channels,
                                      self.cfg.tile_overlap_x_percent,
                                      self.cfg.tile_overlap_y_percent,
                                      self.cfg.tile_prefix,
                                      self.cfg.compressor_chunk_size,
                                      self.cfg.local_storage_dir,
                                      # TODO: how to make these config based?
                                      self.img_storage_dir,
                                      self.deriv_storage_dir)

    def collect_volumetric_image(self, volume_x_um: float, volume_y_um: float,
                                 volume_z_um: float,
                                 channels: list,
                                 tile_overlap_x_percent: float,
                                 tile_overlap_y_percent: float,
                                 tile_prefix: str,
                                 compressor_chunk_size: int = None,
                                 local_storage_dir: Path = Path("."),
                                 img_storage_dir: Path = None,
                                 deriv_storage_dir: Path = None):
        """Collect a tiled volumetric image with specified size/overlap specs.

        :param image_stack_chunk_size:
        """
        mem_chunk = self.cfg.compressor_chunk_size \
            if compressor_chunk_size is None else compressor_chunk_size
        try:  # Ensure we have enough memory for the allocated chunk size.
            self.check_system_memory_resources(len(channels), mem_chunk)
        except MemoryError as e:
            self.log.error(e)
            raise
        # TODO: Ensure we do not exceed volume based on value to tile.

        # Iterate through the volume through z, then x, then y.
        # Play waveforms for the laser, camera trigger, and stage trigger.
        # Capture the fully-formed images as they arrive.

        # Compute: micrometers per grid step. At 0 tile overlap, this is just
        # the sensor's field of view.
        x_grid_step_um = \
            (1 - tile_overlap_x_percent/100.0) * self.cfg.tile_size_x_um
        y_grid_step_um = \
            (1 - tile_overlap_y_percent/100.0) * self.cfg.tile_size_y_um
        # Compute step and tile count.
        # Always round up so that we cover the desired imaging region.
        xsteps = ceil((volume_x_um - self.cfg.tile_size_x_um)
                      / x_grid_step_um)
        ysteps = ceil((volume_y_um - self.cfg.tile_size_y_um)
                      / y_grid_step_um)
        zsteps = ceil((volume_z_um - self.cfg.z_step_size_um)
                      / self.cfg.z_step_size_um)
        xtiles, ytiles, ztiles = (1 + xsteps, 1 + ysteps, 1 + zsteps)
        self.total_tiles = xtiles * ytiles * ztiles * len(channels)

        # TODO: external disk space checks.

        # Reset the starting location.
        self.sample_pose.home_in_place()
        self.stage_x_pos, self.stage_y_pos = (0, 0)
        stage_z_pos = 0
        z_backup_pos = -UM_TO_STEPS*self.cfg.stage_backlash_reset_dist_um
        self.log.debug("Applying extra move to take out backlash.")
        self.sample_pose.move_absolute(z=round(z_backup_pos), wait=True)
        self.sample_pose.move_absolute(z=stage_z_pos, wait=True)
        # Iterate through the volume; create stacks of tiles along the z axis.
        for y in range(ytiles):
            self.sample_pose.move_absolute(y=round(stage_y_pos), wait=True)
            stage_x_pos = 0
            for x in range(xtiles):
                self.sample_pose.move_absolute(x=round(stage_x_pos), wait=True)
                self.log.info(f"x_tile {x}, y_tile: {y}, stage_position: " \
                              f"({self.stage_x_pos:.3f}[um], " \
                              f"{self.stage_y_pos:.3f}[um])")
                stack_prefix = f"{tile_prefix}_" \
                               f"{self.stage_x_pos}_{self.stage_y_pos}"
                self._collect_tile_stacks(channels, ztiles, mem_chunk,
                                          stack_prefix, img_storage_dir,
                                          deriv_storage_dir)
                self.stage_x_pos += y_grid_step_um * UM_TO_STEPS
            self.stage_y_pos += z_grid_step_um * UM_TO_STEPS

    def _collect_tile_stacks(self, channels: list, frame_count: int,
                             compressor_chunk_size: int,
                             stack_prefix: str, image_storage_dir: Path,
                             deriv_storage_dir: Path):
        """Collect tile stack for every specified channel.

        The DAQ is already configured to play each laser and then move the
        stage for a specified amount of frames. This func simply collects all
        the images and then sends them to an external process (in chunks at a
        time) to compress them online and write them to disk.

        Since a single image can be ~300[MB], a stack of frames can
        easily be gigabytes.

        :param channels: a list of channels
        :param frame_count: number of frames to collect into a stack.
        :param compressor_chunk_size: the number of batch frames to send to
            the external compression process at a time.
        """
        # TODO: Put the backlash in a known state.
        stage_z_pos = 0
        self.sample_pose.move_absolute(z=round(stage_z_pos), wait=True)
        self.setup_imaging_hardware()
        # Create storage containers (in ram) for a tile chunk per-channel.
        # TODO: if we have enough memory, implement this as a double buffer
        #   with SharedMemory. ImarisWriter can be invoked in another process.
        # TODO: change this to x,y,z if possible. Consider how it arrives
        #   from eGrabber.
        images = {}
        mip = {}
        tile_name = {}
        for ch in channels:
            tile_name[ch] = f"{stack_prefix}_{ch}"
            # Note: a stack of 128 frames is ~36[GB] in memory.
            images[ch] = np.zeros((compressor_chunk_size,
                                   self.cfg.row_count_pixels,
                                   self.cfg.column_count_pixels),
                                  dtype=self.cfg.datatype)
            mip[ch] = np.zeros((self.cfg.row_count_pixels,
                                self.cfg.column_count_pixels),
                               dtype=self.cfg.datatype)
            # Create/Configure per-channel processes.
            self.stack_writer_worker[ch] = StackWriter()
            # TODO: move many of these params to the StackWriter __init__.
            self.stack_writer_worker[ch].configure(
                self.cfg.row_count_pixels, self.cfg.column_count_pixels,
                frame_count, self.cfg.compressor_chunk_size,
                self.cfg.compressor_thread_count, self.cfg.compressor_style,
                self.cfg.datatype, self.img_storage_dir,
                tile_name[ch], str(ch),
                self.cfg.channel_specs[ch]['hex_color'])
            self.stack_transfer_worker[ch] = FileTransfer()
            self.stack_transfer_worker[ch].configure(self.cfg)
            self.mip_worker[ch] = MIPProcessor()  # has no configure()

        # data_logger is for the camera. It needs to exist betweeen:
        #   cam.start() and cam.stop()
        self.data_logger_worker = DataLogger()
        self.data_logger_worker.configure(self.cfg, f"{stack_prefix}_log")

        # For speed, data is transferred in chunks of a specific size.
        tile_num = 0  # The current frame we're on (channel agnostic).
        buffer_frame_num = 0
        chunk_num = 0
        try:
            start_time = perf_counter()
            # TODO: wait for data_logger to actually start.
            self.data_logger_worker.start()
            self.cam.start(live=False)
            self.ni.start()
            # Note: we assume that these arrive in order, and that we don't
            #   drop any.
            while tile_num < frame_count:
                for ch in channels:
                    # TODO: write this frame directly into shared memory at the
                    #  right offset.
                    images[ch][buffer_frame_num] = self.cam.grab_frame()
                    self.cam.print_statistics(ch)
                    tile_num += 1
                buffer_frame_num += 1
                # Dispatch chunk if we have aggregated a full chunk of frames.
                # OR if we are dispatching the last chunk, and it's not a
                #   multiple of the chunk.
                if buffer_frame_num % compressor_chunk_size == 0:
                    for ch in channels:
                        self.stack_writer_worker[ch].write_block(images[ch], chunk_num)
                        # Update the mip from the mip of the current chunk.
                        if tile_num > compressor_chunk_size:
                            mip[ch] = self.data_processor[ch].update_max_project(mip[ch])
                        self.data_processor[ch].max_project(images[ch])
                    buffer_frame_num = 0
                    chunk_num += 1
                # Dispatch the last chunk if it's not a chunk size multiple.
                elif tile_num == frame_count - 1:
                    for ch in channels:
                        self.stack_writer_worker[ch].write_block(images[ch], chunk_num)
                        self.data_processor[ch].max_project(images[ch])
                        mip[ch] = self.data_processor[ch].update_max_project(mip[ch])
        finally:
            self.ni.stop()
            self.ni.close()
            self.cam.stop()
            # TODO: make sure we pull all the camera images out.
            # TODO: make sure this actually kills the data_logger
            self.data_logger.stop()
            self.data_logger.close()

            # Apply lead-in move to take out z backlash.
            z_backup_pos = -UM_TO_STEPS*self.cfg.stage_backlash_reset_dist_um
            self.log.debug("Applying extra move to take out backlash.")
            self.sample_pose.move_absolute(z=round(z_backup_pos), wait=True)
            self.sample_pose.move_absolute(z=0, wait=True)

            for ch in self.cfg.channels:
                # FIXME: fix naming of tiles here.
                self.stack_writer_worker[ch].close(ch, y_tile, z_tile)
                self.data_processor[ch].close()
            self.log.debug(f"imaging time: {str((perf_counter()-start_time)/3600)}")

            # Write MIPs to files.
            for ch in channels:
                mip_path = deriv_storage_dir / Path(f"{stack_prefix}_mip.tiff")
                # TODO: use the same tiff writer that the mesospim uses.
                imwrite(mip_path, mip[ch])
            if tile_num > 0:
                self.file_transfer.wait()
                self.file_transfer.close()
                for ch in channels:
                    os.remove(self.cfg.source_path + previous_tile_name[ch] + '.ims')
                    os.remove(self.cfg.source_path + previous_tile_name[ch] + '_mip.tiff')
            # FIXME: y_tile, z_tile.
            # TODO: what is this string used for?
            self.file_transfer.start("tile_x_{y_tile:0>4d}_y_{z_tile:0>4d}")
            # TODO: the file transfer process should handle deleting.
            if tile_num == frame_count - 1:
                self.file_transfer.wait()
                self.file_transfer.close()
                for ch in channels:
                    os.remove(self.cfg.source_path + tile_name[ch] + '.ims')
                    os.remove(self.cfg.source_path + tile_name[ch] + '_mip.tiff')

            previous_tile_name = tile_name

    def livestream(self):
        pass

    def close(self):
        """Safely close all open hardware connections."""
        # stuff here.
        self.log.info("Closing NIDAQ connection.")
        self.ni.close()
        # TODO: power down lasers.
        super().close()  # Call this last.
