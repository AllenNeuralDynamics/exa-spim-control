"""Abstraction of the ExaSPIM Instrument."""

import numpy as np
import logging
from tqdm import tqdm
from pathlib import Path
from psutil import virtual_memory, Process
from os import getpid
from time import perf_counter, sleep
from mock import NonCallableMock as Mock
from datetime import datetime
from exaspim.exaspim_config import ExaspimConfig
from exaspim.devices.camera import Camera
from exaspim.devices.ni import NI
from exaspim.operations.waveform_generator import generate_waveforms
from exaspim.operations.gpu_img_downsample import DownSample
from threading import Event
from exaspim.processes.stack_writer import StackWriter
from exaspim.processes.file_transfer import FileTransfer
from exaspim.data_structures.shared_double_buffer import SharedDoubleBuffer
from math import ceil, floor
from tigerasi.tiger_controller import TigerController, STEPS_PER_UM
from tigerasi.sim_tiger_controller import SimTigerController as SimTiger
from spim_core.spim_base import Spim, lock_external_user_input
from spim_core.devices.tiger_components import SamplePose
from egrabber import query

# Constants
IMARIS_TIMEOUT_S = 0.1


class Exaspim(Spim):

    def __init__(self, config_filepath: str, simulated: bool = False):
        super().__init__(config_filepath, simulated)
        self.cfg = ExaspimConfig(config_filepath)
        # Separate Processes per channel.
        self.mip_workers = {}  # aggregates xy, xy, yz MIPs from frames.
        self.stack_writer_workers = {}  # writes img chunks to a stack on disk.
        # Containers
        self.img_buffers = {}  # Shared double buffers for acquisition & compression.
        # Hardware
        self.cam = Camera(self.cfg) if not self.simulated else Mock(Camera)
        self.ni = NI(**self.cfg.daq_obj_kwds) if not self.simulated else Mock(NI)
        self.etl = None
        self.gavlo_a = None
        self.gavlo_b = None
        self.daq = None
        self.tigerbox = TigerController(**self.cfg.tiger_obj_kwds) if not \
            self.simulated else SimTiger(**self.cfg.tiger_obj_kwds,
                                         build_config={'Motor Axes': ['X', 'Y', 'Z', 'M', 'N', 'W', 'V']})
        self.sample_pose = SamplePose(self.tigerbox,
                                      **self.cfg.sample_pose_kwds)
        # Extra Internal State attributes for the current image capture
        # sequence. These really only need to persist for logging purposes.
        self.frame_index = 0  # current image to capture.
        self.total_tiles = 0  # tiles to be captured.
        self.downsampler = DownSample()
        self.prev_frame_chunk_index = None  # chunk index of most recent frame.
        self.stage_x_pos_um = None  # Current x position in [um]
        self.stage_y_pos_um = None  # Current y position in [um]
        self.stage_z_pos_um = None  # Current z position in [um]
        self.start_pos = None  # Start position of scan
        self.livestream_enabled = Event()
        self.acquiring_images = False
        self.active_lasers = None
        # Setup hardware according to the config.
        self._setup_motion_stage()
        self._setup_camera()

    def _setup_motion_stage(self):
        """Configure the sample stage according to the config."""
        # Disable backlash compensation.
        self.sample_pose.set_axis_backlash(z=0)

    def __simulated_grab_frame(self):
        elapsed_time = perf_counter() - self.last_frame_time
        if elapsed_time < 1. / 6.4:
            remaining_time = 1. / 6.4 - elapsed_time
            sleep(remaining_time)
        self.last_frame_time = perf_counter()
        # Image shape is a buffer organized by y and then by x.
        return np.zeros((self.cfg.sensor_row_count,
                         self.cfg.sensor_column_count),
                        dtype=self.cfg.image_dtype)

    def _setup_camera(self):
        """Configure the camera according to the config."""
        # TODO: pass in config parameters here instead of passing in cfg on init.
        self.cam.configure()
        if self.simulated:
            self.last_frame_time = perf_counter()
            self.cam.get_camera_acquisition_state.return_value = {'dropped_frames': 0}
            self.cam.grab_frame = self.__simulated_grab_frame
            self.cam.get_mainboard_temperature.return_value = 23.15
            self.cam.get_sensor_temperature.return_value = 23.15

    def _setup_waveform_hardware(self, wavelengths: list[int], live: bool = False):

        self.active_lasers = wavelengths
        self.log.info("Configuring NIDAQ")
        self.ni.configure(live=live)
        self.log.info("Generating waveforms.")
        voltages_t = generate_waveforms(self.cfg, plot=True, channels=self.active_lasers, live=live)
        self.log.info("Writing waveforms to hardware.")
        self.ni.assign_waveforms(voltages_t)

    def _check_system_memory_resources(self, channel_count: int,
                                       mem_chunk: int):
        """Make sure this machine can image under the specified configuration.

        :param channel_count: the number of channels we want to image with.
        :param mem_chunk: the number of images to hold in one chunk for
            compression
        :raises MemoryError:
        """
        # Calculate double buffer size for all channels.
        bytes_per_gig = (1024 ** 3)
        used_mem_gigabytes = \
            ((self.cfg.bytes_per_image * mem_chunk * 2) / bytes_per_gig) \
            * channel_count
        # TODO: we probably want to throw in 1-2gigs of fudge factor.
        free_mem_gigabytes = virtual_memory()[1] / bytes_per_gig
        if free_mem_gigabytes < used_mem_gigabytes:
            raise MemoryError("System does not have enough memory to run "
                              "the specified number of channels. "
                              f"{used_mem_gigabytes:.1f}[GB] are required but "
                              f"{free_mem_gigabytes:.1f}[GB] are available.")

    def apply_config(self):
        """Apply the new state present in the config."""
        # Check to see what changed and apply the new changes safely.
        # TODO: pull changes from config and apply them directly in a safe way.
        #   Throw an error otherwise.
        # TODO: lockout access to state changes if we are unable to change them
        #   i.e: we are acquiring images and cannot change the hardware settings.

        if self.acquiring_images:
            raise RuntimeError("Cannot change system configuration while "
                               "acquiring images.")
        if self.livestream_enabled:
            self.cam.stop()
        self.cam.configure()  # configures from config.
        if self.livestream_enabled:
            active_lasers = self.active_lasers
            self.stop_livestream()
            self.start_livestream(active_lasers)  # reapplies waveform settings.

    def log_system_metadata(self):
        # log tiger settings
        self.log.info('tiger motorized axes parameters',
                      extra={'tags': ['schema']})
        build_config = self.tigerbox.get_build_config()
        self.log.debug(f'{build_config}')
        ordered_axes = build_config['Motor Axes']
        for axis in ordered_axes:
            axis_settings = self.tigerbox.get_info(axis)
            for setting in axis_settings:
                self.log.info(f'{axis} axis, {setting}, {axis_settings[setting]}',
                              extra={'tags': ['schema']})

        if self.simulated:
            return
        # log egrabber camera settings
        self.log.info('egrabber camera parameters', extra={'tags': ['schema']})
        categories = self.cam.grabber.device.get(query.categories())
        for category in categories:
            features = self.cam.grabber.device.get(query.features_of(category))
            for feature in features:
                if self.cam.grabber.device.get(query.available(feature)):
                    if self.cam.grabber.device.get(query.readable(feature)):
                        if not self.cam.grabber.device.get(query.command(feature)):
                            self.log.info(f'device, {feature}, {self.cam.grabber.device.get(feature)}',
                                          extra={'tags': ['schema']})

        categories = self.cam.grabber.remote.get(query.categories())
        for category in categories:
            features = self.cam.grabber.remote.get(query.features_of(category))
            for feature in features:
                if self.cam.grabber.remote.get(query.available(feature)):
                    if self.cam.grabber.remote.get(query.readable(feature)):
                        if not self.cam.grabber.remote.get(query.command(feature)):
                            if feature != "BalanceRatioSelector" and feature != "BalanceWhiteAuto":
                                self.log.info(f'remote, {feature}, {self.cam.grabber.remote.get(feature)}',
                                              extra={'tags': ['schema']})

        categories = self.cam.grabber.stream.get(query.categories())
        for category in categories:
            features = self.cam.grabber.stream.get(query.features_of(category))
            for feature in features:
                if self.cam.grabber.stream.get(query.available(feature)):
                    if self.cam.grabber.stream.get(query.readable(feature)):
                        if not self.cam.grabber.stream.get(query.command(feature)):
                            self.log.info(f'stream, {feature}, {self.cam.grabber.stream.get(feature)}',
                                          extra={'tags': ['schema']})

        categories = self.cam.grabber.interface.get(query.categories())
        for category in categories:
            features = self.cam.grabber.interface.get(query.features_of(category))
            for feature in features:
                if self.cam.grabber.interface.get(query.available(feature)):
                    if self.cam.grabber.interface.get(query.readable(feature)):
                        if not self.cam.grabber.interface.get(query.command(feature)):
                            self.log.info(f'interface, {feature}, {self.cam.grabber.interface.get(feature)}',
                                          extra={'tags': ['schema']})

        categories = self.cam.grabber.system.get(query.categories())
        for category in categories:
            features = self.cam.grabber.system.get(query.features_of(category))
            for feature in features:
                if self.cam.grabber.system.get(query.available(feature)):
                    if self.cam.grabber.system.get(query.readable(feature)):
                        if not self.cam.grabber.system.get(query.command(feature)):
                            self.log.info(f'system, {feature}, {self.cam.grabber.system.get(feature)}',
                                          extra={'tags': ['schema']})

    def run_from_config(self):
        self.collect_volumetric_image(self.cfg.volume_x_um,
                                      self.cfg.volume_y_um,
                                      self.cfg.volume_z_um,
                                      self.cfg.channels,
                                      self.cfg.tile_overlap_x_percent,
                                      self.cfg.tile_overlap_y_percent,
                                      self.cfg.z_step_size_um,
                                      self.cfg.tile_prefix,
                                      self.cfg.compressor_chunk_size,
                                      self.cache_storage_dir,
                                      # TODO: make these last two config based.
                                      self.img_storage_dir,
                                      self.deriv_storage_dir)

    @lock_external_user_input
    def collect_volumetric_image(self, volume_x_um: float, volume_y_um: float,
                                 volume_z_um: float,
                                 channels: list[int],
                                 tile_overlap_x_percent: float,
                                 tile_overlap_y_percent: float,
                                 z_step_size_um: float,
                                 tile_prefix: str,
                                 compressor_chunk_size: int = None,
                                 local_storage_dir: Path = Path("."),
                                 img_storage_dir: Path = None,
                                 deriv_storage_dir: Path = None):
        # TODO: pass in start position as a parameter.
        """Collect a volumetric image with specified size/overlap specs."""
        # Memory checks.
        chunk_size = self.cfg.compressor_chunk_size \
            if compressor_chunk_size is None else compressor_chunk_size
        try:  # Ensure we have enough memory for the allocated chunk size.
            self._check_system_memory_resources(len(channels), chunk_size)
        except MemoryError as e:
            self.log.error(e)
            raise
        x_grid_step_um, y_grid_step_um = self.get_xy_grid_step(tile_overlap_x_percent,
                                                               tile_overlap_y_percent)
        xtiles, ytiles, ztiles = self.get_tile_counts(tile_overlap_x_percent,
                                                      tile_overlap_y_percent,
                                                      z_step_size_um,
                                                      volume_x_um, volume_y_um,
                                                      volume_z_um)
        self.log.debug(f"Grid step: {x_grid_step_um:.3f}[um] in x, "
                       f"{y_grid_step_um:.3f}[um] in y.")
        self.log.debug(f"Imaging operation will produce: "
                       f"{xtiles} xtiles, {ytiles} ytiles, and {ztiles} ztiles"
                       f"per channel.")
        # Log relevant info about this imaging run.
        acquisition_params = \
            {
                'local_storage_directory': str(local_storage_dir),
                'external_storage_directory': str(img_storage_dir),
                'specimen_id': self.cfg.imaging_specs['subject_id'],
                'subject_id': self.cfg.imaging_specs['subject_id'],
                'instrument_id': 'exaspim-01',
                'chamber_immersion_medium': self.cfg.immersion_medium,
                'chamber_immersion_refractive_index': self.cfg.immersion_medium_refractive_index,
                'tags': ['schema']
            }
        self.log.info("acquisition parameters", extra=acquisition_params)
        self.log.info("Session start.", extra={'tags': ['schema']})
        self.log_system_metadata()
        # Update internal state.
        self.total_tiles = xtiles * ytiles * ztiles * len(channels)
        self.log.debug(f"Total tiles: {self.total_tiles}.")
        self.frame_index = 0  # Reset image index.
        self.acquiring_images = True
        start_time = perf_counter()  # For logging elapsed time.
        # Setup containers
        stack_transfer_workers = {}  # moves z-stacks to destination folder.
        self._setup_waveform_hardware(channels)
        # Move sample to preset starting position if specified.
        # TODO: pass this in as a parameter.
        if self.start_pos is not None:
            self.sample_pose.move_absolute(self.start_pos)
            self.start_pos = None
        # Reset the starting location.
        self.sample_pose.zero_in_place('x', 'y', 'z')
        # (ytiles-1)*y_grid_step_um
        self.stage_x_pos_um, self.stage_y_pos_um, self.stage_z_pos_um = (0, 0, 0) # TODO, this changes for reversing tiling
        # Iterate through the volume through z, then x, then y.
        # Play waveforms for the laser, camera trigger, and stage trigger.
        # Capture the fully-formed images as they arrive.
        # Create stacks of tiles along the z axis per channel.
        # Transfer stacks as they arrive to their final destination.
        self.log.info('tile parameters', extra={'tags': ['schema']})
        try:
            for x in tqdm(range(xtiles), desc="XY Tiling Progress"):
                self.sample_pose.move_absolute(
                    x=round(self.stage_x_pos_um * STEPS_PER_UM), wait=True)
                self.stage_y_pos_um = 0 # TODO, this changes for reversing tiling
                for y in range(ytiles):
                    self.sample_pose.move_absolute(
                        y=round(self.stage_y_pos_um * STEPS_PER_UM), wait=True)
                    start_tile = 0
                    tile_number = y + x*ytiles
                    if tile_number >= start_tile:
                        self.log.info(f"tile: ({x}, {y}); stage_position: "
                                      f"({self.stage_x_pos_um:.3f}[um], "
                                      f"{self.stage_y_pos_um:.3f}[um])")
                        stack_prefix = f"{tile_prefix}_x_{x:04}_y_{y:04}_z_0000"
                        # Logging for JSON schema
                        etl_temperature = self.tigerbox.get_etl_temp('V')  # TODO: this is hardcoded as V axis right now
                        camera_temperature = self.cam.get_mainboard_temperature()
                        sensor_temperature = self.cam.get_sensor_temperature()
                        tile_schema_params = \
                            {
                                'tile_number': tile_number,
                                'etl_temperature': etl_temperature,
                                'etl_temperature_units': 'C',
                                'camera_board_temperature': camera_temperature,
                                'camera_board_temperature_units': 'C',
                                'sensor_temperature': sensor_temperature,
                                'sensor_temperature_units': 'C',
                                'tags': ['schema']
                            }
                        self.log.info('Tile Data', extra=tile_schema_params)
                        # Log file params per laser channel.
                        for laser in self.active_lasers:
                            file_schema_data = \
                                {
                                    'file_name': f'{stack_prefix}_ch_{laser}.ims',
                                    'channel_name': f'{laser}',
                                    'x_voxel_size': self.cfg.tile_size_x_um / self.cfg.sensor_column_count,
                                    'y_voxel_size': self.cfg.tile_size_y_um / self.cfg.sensor_row_count,
                                    'z_voxel_size': z_step_size_um,
                                    'voxel_size_units': 'micrometers',
                                    'tile_x_position': self.stage_x_pos_um * 0.001,
                                    'tile_y_position': self.stage_y_pos_um * 0.001,
                                    'tile_z_position': self.stage_z_pos_um * 0.001,
                                    'tile_position_units': 'millimeters',
                                    'lightsheet_angle': 0,
                                    'lightsheet_angle_units': 'degrees',
                                    'laser_wavelength': laser,
                                    'laser_wavelength_units': "nanometers",
                                    'laser_power': 2000,
                                    'laser_power_units': 'milliwatts',
                                    'filter_wheel_index': 0,
                                    'tags': ['schema']
                                }
                            laser = str(laser)
                            for key in self.cfg.channel_specs[laser]['etl']:
                                file_schema_data[f'daq_etl {key}'] = f'{self.cfg.channel_specs[laser]["etl"][key]}'
                            for key in self.cfg.channel_specs[laser]['galvo_a']:
                                file_schema_data[f'daq_galvo_a {key}'] = f'{self.cfg.channel_specs[laser]["galvo_a"][key]}'
                            for key in self.cfg.channel_specs[laser]['galvo_b']:
                                file_schema_data[f'daq_galvo_b {key}'] = f'{self.cfg.channel_specs[laser]["galvo_b"][key]}'
                            self.log.info(f'Laser Channel {laser} File Data',
                                          extra=file_schema_data)

                        output_filenames = \
                            self._collect_zstacks(channels, ztiles, z_step_size_um,
                                                  chunk_size, local_storage_dir,
                                                  stack_prefix)

                        # Start transferring zstack file to its destination.
                        # Note: Image transfer should be faster than image capture,
                        #   but we still wait for prior process to finish.
                        if stack_transfer_workers:
                            self.log.info("Waiting for zstack transfer processes "
                                          "to complete.")
                            for channel in list(stack_transfer_workers.keys()):
                                worker = stack_transfer_workers.pop(channel)
                                worker.join()
                        # Kick off Stack transfer processes per channel.
                        # Bail if we don't need to transfer anything.
                        if img_storage_dir:
                            for channel, filename in output_filenames.items():
                                self.log.info(f"Starting transfer process for {filename}.")
                                stack_transfer_workers[channel] = \
                                    FileTransfer(local_storage_dir / filename,
                                                 img_storage_dir / filename,
                                                 self.cfg.ftp, self.cfg.ftp_flags)
                                stack_transfer_workers[channel].start()
                        else:
                            self.log.info("Skipping file transfer process. File "
                                          "is already at its destination.")
                    self.stage_y_pos_um = self.stage_y_pos_um + y_grid_step_um # TODO, this changes for reversing tiling
                self.stage_x_pos_um = self.stage_x_pos_um + x_grid_step_um # TODO, this changes for reversing tiling
            # Acquisition cleanup.
            self.log.info(f"Total imaging time: "
                          f"{(perf_counter() - start_time) / 3600.:.3f} hours.")
        except Exception:
            self.log.exception("Error raised from the main acquisition loop.")
            raise
        finally:
            self.sample_pose.move_absolute(x=0, y=0, wait=True)
            # Cleanup internal state.
            self.acquiring_images = False
        # Write MIPs to files.
        # TODO: in the file_prefix, indicate if it is a XY, XZ, or YZ mip.
        # for ch, mip_data in mips.items():
        #    path = deriv_storage_dir/Path(f"{stack_prefix}_{ch}_mip.tiff")
        #    self.log.debug(f"Writing MIP for {ch} channel to: {path}")
        #    with TiffWriter(path, bigtiff=True) as tif:
        #        tif.write(mip_data)
        self.log.info('Session end.', extra={'tags': ['schema']})

    def _collect_zstacks(self, channels: list[int], frame_count: int,
                         z_step_size_um: float, chunk_size: int,
                         local_storage_dir: Path,
                         stack_prefix: str):
        """Collect tile stack for every specified channel and write them to
        disk compressed through ImarisWriter.

        The DAQ is already configured to play each laser and then move the
        stage for a specified amount of frames. This func simply deserializes
        all the incoming images into separate channels, buffers them into
        chunks, and then sends them to ImarisWriter in an external process
        (in chunks at a time) to compress them online and write them to disk.

        ImarisWriter operates fastest when operating on larger chunks at once.
        We allocate shared memory to hold space for 2 chunks per channel, one
        to write to, and one for ImarisWriter to compress in parallel.

        Note: Since a single image can be ~300[MB], a stack of frames can
        easily be tens of gigabytes.

        :param channels: a list of channels
        :param frame_count: number of frames to collect into a stack.
        :param z_step_size_um: spacing between each step.
        :param chunk_size: the number of batch frames to send to
            the external compression process at a time.
        :param local_storage_dir: the location to write the zstacks to.
        :param stack_prefix: the filename prefix. ('_<channel>.ims' will be
            appended to it.)

        :return: dict, keyed by channel name, of the filenames written to disk.
        """
        self.log.debug(f"Stack Capture starting memory usage: {self.get_mem_consumption():.3f}%")
        stack_file_names = {}  # names of the files we will create.
        # Flow Control flags.
        capture_successful = False
        # Put the backlash into a known state.
        stage_z_pos = 0
        z_backup_pos = -STEPS_PER_UM * self.cfg.stage_backlash_reset_dist_um
        self.log.debug("Applying extra move to take out backlash.")
        self.sample_pose.move_absolute(z=round(z_backup_pos))
        self.sample_pose.move_absolute(z=round(stage_z_pos))
        self.sample_pose.setup_ext_trigger_linear_move('z', frame_count,
                                                       z_step_size_um / 1.0e3)
        # Allocate shard memory and create StackWriter per-channel.
        for ch in channels:
            stack_file_names[ch] = f"{stack_prefix}_ch_{ch}.ims"
            mem_shape = (chunk_size,
                         self.cfg.sensor_row_count,
                         self.cfg.sensor_column_count)
            self.img_buffers[ch] = SharedDoubleBuffer(mem_shape,
                                                      dtype=self.cfg.datatype)
            chunk_dim_order = ('z', 'y', 'x')  # must agree with mem_shape
            self.log.debug(f"Creating StackWriter for {ch}[nm] channel.")
            self.stack_writer_workers[ch] = \
                StackWriter(self.cfg.sensor_row_count,
                            self.cfg.sensor_column_count,
                            frame_count, self.stage_x_pos_um, self.stage_y_pos_um,
                            self.cfg.x_voxel_size_um, self.cfg.y_voxel_size_um,
                            self.cfg.z_step_size_um,
                            self.cfg.compressor_chunk_size,
                            chunk_dim_order,
                            self.cfg.compressor_thread_count,
                            self.cfg.compressor_style,
                            self.cfg.datatype, local_storage_dir,
                            stack_file_names[ch], str(ch),
                            self.cfg.channel_specs[str(ch)]['hex_color'])
            self.stack_writer_workers[ch].start()
        chunk_count = ceil(frame_count / chunk_size)
        last_frame_index = frame_count - 1
        remainder = frame_count % chunk_size
        last_chunk_size = chunk_size if not remainder else remainder
        start_time = perf_counter()
        self.cam.start(len(channels) * frame_count, live=False)  # TODO: rewrite to block until ready.
        try:
            # Images arrive serialized in repeating channel order.
            for stack_index in tqdm(range(frame_count), desc="ZStack progress"):
                chunk_index = stack_index % chunk_size
                # Start a batch of pulses to generate more frames and movements.
                if chunk_index == 0:
                    chunks_filled = floor(stack_index / chunk_size)
                    remaining_chunks = chunk_count - chunks_filled
                    num_pulses = last_chunk_size if remaining_chunks == 1 else chunk_size
                    self.log.debug(f"Grabbing chunk {chunks_filled + 1}/{chunk_count}")
                    self.log.debug(f"Current memory usage: {self.get_mem_consumption():.3f}%")
                    self.ni.set_pulse_count(num_pulses)
                    self.ni.start()
                # Deserialize camera input into corresponding channel.
                for ch_index in channels:
                    self.log.debug(f"Grabbing frame "
                                   f"{stack_index + 1:9}/{frame_count} for "
                                   f"{ch_index}[nm] channel.")
                    self.img_buffers[ch_index].write_buf[chunk_index] = \
                        self.cam.grab_frame()
                    self._check_camera_acquisition_state()
                # Save the index of the most-recently captured frame to
                # offer it to a live display upon request.
                self.prev_frame_chunk_index = chunk_index
                self.frame_index += 1
                # Dispatch either a full chunk of frames or the last chunk,
                # which may not be a multiple of the chunk size.
                if chunk_index == chunk_size - 1 or stack_index == last_frame_index:
                    self.ni.stop(wait=True)
                    # Wait for z stack writing to finish before dispatching
                    # more data.
                    if not self._all_stack_workers_idle():
                        final = "final " if stack_index == last_frame_index else ""
                        self.log.warning(f"Waiting for {final}chunk to be "
                                         f"compressed to disk.")
                    while not self._all_stack_workers_idle():
                        sleep(0.001)
                    # Dispatch chunk to each StackWriter compression process.
                    # Toggle double buffer to continue writing images.
                    # To read the new data, the StackWriter needs the name of
                    # the current read memory location and a trigger to start.
                    for ch_index in channels:
                        self.img_buffers[ch_index].toggle_buffers()
                        self.stack_writer_workers[ch_index].shm_name = \
                            self.img_buffers[ch_index].read_buf_mem_name
                        self.stack_writer_workers[ch_index].done_reading.clear()
            capture_successful = True
            self.log.debug(f"Stack imaging time: "
                           f"{(perf_counter() - start_time) / 3600.:.3f} hours.")
        except Exception:
            self.log.exception("Error raised from the stack acquisition loop.")
            raise
        finally:
            self.log.debug("Closing devices and processes for this stack.")
            self.ni.stop(wait=True)
            self.cam.stop()
            # Wait for stack writers to finish writing files to disk if capture
            # was successful.
            timeout = None if capture_successful else IMARIS_TIMEOUT_S
            for ch_name, worker in self.stack_writer_workers.items():
                force_c = "Force C" if not capture_successful else "C"
                msg = f"{force_c}losing {ch_name}[nm] channel StackWriter."
                level = logging.DEBUG if capture_successful else logging.WARNING
                self.log.log(level, msg)
                worker.join(timeout=timeout)
                # TODO: process termination upon failure?
            # TODO: flag a thread-safe event that we are no longer able to livestream.
            for ch in list(self.img_buffers.keys()):
                self.log.debug(f"Deallocating {ch}[nm] stack shared double buffer.")
                self.img_buffers[ch].close_and_unlink()
                del self.img_buffers[ch]
            # Leave the sample in the starting position.
            # Apply lead-in move to take out z backlash.
            z_backup_pos = -STEPS_PER_UM * self.cfg.stage_backlash_reset_dist_um
            self.log.debug("Applying extra move to take out backlash.")
            self.sample_pose.move_absolute(z=round(z_backup_pos))
            self.sample_pose.move_absolute(z=0)
            self.log.debug(f"Stack Capture ending memory usage: {self.get_mem_consumption():.3f}%")
        return stack_file_names

    def _all_stack_workers_idle(self):
        """Helper function. True if all StackWriters are idle."""
        return all([w.done_reading.is_set()
                    for _, w in self.stack_writer_workers.items()])

    def _check_camera_acquisition_state(self):
        """Get the current eGrabber state. Raise a runtime error if we drop frames."""
        state = self.cam.get_camera_acquisition_state()  # logs it.
        if state['dropped_frames'] > 0:
            msg = "Acquisition loop has dropped a frame."
            self.log.error(msg)
            raise RuntimeError(msg)

    def _compute_mip_shapes(self, volume_x: float, volume_y: float,
                            volume_z: float, percent_x_overlap: float,
                            percent_y_overlap: float):
        """return three 2-tuples indicating the shapes of the mips."""
        raise NotImplementedError
        # xy, xz, yz = (0,0), (0,0), (0,0)

    def start_livestream(self, wavelength: list[int] = None):

        # Bail early if it's started.
        print(wavelength)
        if self.livestream_enabled.is_set():
            self.log.warning("Not starting. Livestream is already running.")
            return
        self.log.debug("Starting livestream.")
        self.log.warning(f"Turning on the {wavelength}[nm] laser.")
        self._setup_waveform_hardware(wavelength, live=True)
        self.cam.start(live=True)
        self.ni.start()
        self.livestream_enabled.set()
        self.active_lasers = wavelength
        # Launch thread for picking up camera images.

    def _livestream_worker(self, channel: list[int] = None):
        """Return the most recent acquisition image for display elsewhere.

        :param channel: the channel to get the latest image for, or None,
            if only one channel is being imaged.

        :return: downsample pyramid of the most recent image.
        """
        # Return a dummy image if none are available.
        channel_id = 0
        while self.livestream_enabled.is_set():
            channel_id = (channel_id + 1) % len(self.active_lasers) if len(self.active_lasers) != 1 else 0
            yield self.get_latest_image(self.active_lasers[channel_id]), self.active_lasers[channel_id]

    def stop_livestream(self):
        # Bail early if it's already stopped.
        if not self.livestream_enabled.is_set():
            self.log.warning("Not stopping. Livestream is already stopped.")
            return
        self.livestream_enabled.clear()
        self.cam.stop()
        self.ni.stop(wait=False)
        sleep(1)  # This is a hack.
        self.ni.close()
        self.active_lasers = None

    def lock_external_user_input(self):
        """Lockout any user inputs such that they have no effect."""
        self.sample_pose.lock_external_user_input()

    def unlock_external_user_input(self):
        """Unlock any external user inputs."""
        self.sample_pose.unlock_external_user_input()

    def set_scan_start(self, coords):

        """Set start position of scan. Stage will move to coords via sample pose
        at begining of scan"""
        # FIXME: we should pass a starting position into collect_volumetric_image.
        self.start_pos = coords

    def get_latest_image(self, channel: int = None):
        """Return the most recent acquisition image for display elsewhere.
        :param channel: the channel to get the latest image for, or None,
            if only one channel is being imaged.
        :return: downsample pyramid of the most recent image.
        """
        img_buffer = self.img_buffers.get(channel, None)  # Not None during acquisition.
        if img_buffer:
            return self.downsampler.compute(img_buffer.write_buf[self.prev_frame_chunk_index])
        # Return a dummy image if none are available.
        if not img_buffer or self.prev_frame_chunk_index is None:
            if self.livestream_enabled.is_set():
                return self.downsampler.compute(self.cam.grab_frame())
            elif self.simulated:
                # Display "white noise" if no image is available.
                return self.downsampler.compute(np.random.randint(0, 255, size=(self.cfg.sensor_row_count,
                                                                                self.cfg.sensor_column_count),
                                                                  dtype=self.cfg.image_dtype))

    def get_mem_consumption(self):
        """get memory consumption as a percent for this process and all
        child processes."""
        current_process = Process(getpid())
        mem = current_process.memory_percent()
        for child in current_process.children(recursive=True):
            mem += child.memory_percent()
        return mem

    def close(self):
        """Safely close all open hardware connections."""
        # Close any opened shared memory.
        for ch_name, buf in self.img_buffers.items():
            buf.close_and_unlink()
        self.ni.close()
        # TODO: power down hardware.
        super().close()  # Call this last.
