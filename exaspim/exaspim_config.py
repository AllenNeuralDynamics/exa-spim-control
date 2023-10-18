import copy
from pathlib import Path
from spim_core.config_base import SpimConfig

# A template from which we can define a blank exaspim config.
# TODO: create this.
TomlTemplate = {}


class ExaspimConfig(SpimConfig):

    def __init__(self, toml_filepath: str):
        super().__init__(toml_filepath, TomlTemplate)

        # Make references to mutable objects.
        self.experiment_specs = self.cfg['experiment_specs']
        self.waveform_specs = self.cfg['waveform_specs']
        self.compressor_specs = self.cfg['compressor_specs']
        self.file_transfer_specs = self.cfg['file_transfer_specs']
        self.stage_specs = self.cfg['sample_stage_specs']
        self.channel_specs = self.cfg['channel_specs']
        self.camera_specs = self.cfg['camera_specs']

        # Keyword arguments for instantiating objects.
        self.joystick_kwds = self.cfg['joystick_kwds']
        self.sample_pose_kwds = self.cfg['sample_pose_kwds']
        self.tiger_obj_kwds = self.cfg['tiger_controller_driver_kwds']
        # Other obj kwds are generated dynamically.

    # Per-channel getter methods.
    def get_channel_cycle_time(self, wavelength: int):
        """Returns required time to play a waveform period for a given channel."""
        return self.camera_exposure_time \
               + self.get_etl_buffer_time(wavelength) \
               + self.frame_rest_time \
               + self.camera_dwell_time

    def get_camera_delay_time(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['camera']['delay_time_s']

    def get_etl_amplitude(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['amplitude']

    def get_galvo_a_setpoint(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['galvo_a']['setpoint']

    def get_galvo_b_setpoint(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['galvo_b']['setpoint']

    def get_etl_offset(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['offset']

    def get_etl_nonlinear(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['nonlinear']

    def get_etl_interp_time(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['interp_time_s']

    def get_etl_buffer_time(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['buffer_time_s']

    # Channel Specs
    def get_channel_ao_voltage(self, wl):
        return self.channel_specs[wl]['ao_voltage']

    def set_channel_ao_voltage(self, wl, value):

        self.channel_specs[wl]['ao_voltage'] = value

    # Waveform Specs
    @property
    def ttl_pulse_time(self):
        return self.waveform_specs['ttl_pulse_time_s']

    @ttl_pulse_time.setter
    def ttl_pulse_time(self, seconds):
        """The "on-period" length of an external TTL trigger pulse."""
        self.waveform_specs['ttl_pulse_time_s'] = seconds

    @property
    def frame_rest_time(self):
        return self.waveform_specs['frame_rest_time_s']

    @frame_rest_time.setter
    def frame_rest_time(self, seconds):
        """The rest time in between frames for the ETL to snap back to its
        starting position."""
        self.waveform_specs['frame_rest_time_s'] = seconds

    # Experiment Specs

    @property
    def experimenters_name(self):
        return self.experiment_specs['experimenters_name']

    @experimenters_name.setter
    def experimenters_name(self, name: str):
        self.experiment_specs['experimenters_name'] = name

    @property
    def immersion_medium(self):
        return self.experiment_specs['immersion_medium']

    @immersion_medium.setter
    def immersion_medium(self, medium: str):
        self.experiment_specs['immersion_medium'] = medium

    @property
    def immersion_medium_refractive_index(self):
        return self.experiment_specs['immersion_medium_refractive_index']

    @immersion_medium_refractive_index.setter
    def immersion_medium_refractive_index(self, ri: float):
        self.experiment_specs['immersion_medium_refractive_index'] = ri

    @property
    def x_anatomical_direction(self):
        """Anatomical orientation along x"""
        return self.experiment_specs['x_anatomical_direction']

    @x_anatomical_direction.setter
    def x_anatomical_direction(self, direction):
        """Anatomical orientation along x"""
        self.experiment_specs['x_anatomical_direction'] = direction
    @property
    def y_anatomical_direction(self):
        """Anatomical orientation along y"""
        return self.experiment_specs['y_anatomical_direction']

    @y_anatomical_direction.setter
    def y_anatomical_direction(self, direction):
        """Anatomical orientation along x"""
        self.experiment_specs['y_anatomical_direction'] = direction
    @property
    def z_anatomical_direction(self):
        """Anatomical orientation along z"""
        return self.experiment_specs['z_anatomical_direction']

    @z_anatomical_direction.setter
    def z_anatomical_direction(self, direction):
        """Anatomical orientation along x"""
        self.experiment_specs['z_anatomical_direction'] = direction
    # Stage Specs
    @property
    def z_step_size_um(self):
        return self.cfg['imaging_specs']['z_step_size_um']

    @z_step_size_um.setter
    def z_step_size_um(self, um: float):
        self.cfg['imaging_specs']['z_step_size_um'] = um

    @property
    def start_tile_index(self):
        """If specified, the tile index from which to start collecting z stacks.

        Note: z stack index must be in the range of [0, xtiles * ytiles - 1].

        Note: z stack index increments first in the y dimension; then in the
        x dimension. i.e: in a grid of 5 xtiles by 3 ytiles, tile "0" is (0, 0),
        tile "2" is (0, 2), tile "3" is (1, 0), etc.
        """
        return self.imaging_specs.get('start_tile_index', None)

    @start_tile_index.setter
    def start_tile_index(self, index: int):
        self.imaging_specs['start_tile_index'] = index

    @property
    def end_tile_index(self):
        """If specified, the tile index from which to stop collecting z stacks,
        i.e: the final stack to be collected. (See details on
        :meth:`start_tile_index` for more details on tile indexing.)
        """
        return self.imaging_specs.get('end_tile_index', None)

    @end_tile_index.setter
    def end_tile_index(self, index):
        self.imaging_specs['end_tile_index'] = index
        
    @property
    def stage_backlash_reset_dist_um(self):
        return self.stage_specs['backlash_reset_distance_um']

    @stage_backlash_reset_dist_um.setter
    def stage_backlash_reset_dist_um(self, micrometers: int):
        self.stage_specs['backlash_reset_distance_um'] = micrometers

    # Camera Specs
    @property
    def egrabber_frame_buffer(self):
        return self.camera_specs['egrabber_frame_buffer']

    @egrabber_frame_buffer.setter
    def egrabber_frame_buffer(self, size: int):
        self.camera_specs['egrabber_frame_buffer'] = size

    @property  # No setter!
    def camera_line_interval_us(self):
        """Camera Line Interval. Cannot be changed."""
        return self.camera_specs['line_interval_us']

    @property
    def slit_width(self):
        """Slit width (in pixels) of the slit that moves along the frame"""
        return self.design_specs['slit_width_pixels']

    @slit_width.setter
    def slit_width(self, pixels):
        self.design_specs['slit_width_pixels'] = pixels

    @property
    def camera_digital_gain(self):
        return self.camera_specs['digital_gain_adu']

    @camera_digital_gain.setter
    def camera_digital_gain(self, adu: float):
        self.camera_specs['digital_gain_adu'] = adu

    # Compressor Specs
    @property
    def compressor_style(self):
        return self.compressor_specs['compression_style']

    @property
    def compressor_thread_count(self):
        return self.compressor_specs['compressor_thread_count']

    @property
    def compressor_chunk_size(self):
        """number of images in a chunk to be compressed at a time."""
        return self.compressor_specs['image_stack_chunk_size']

    # @property
    # def memento_path(self) -> Path:
    #     return Path(self.compressor_specs['memento_executable_path'])
    #
    # @memento_path.setter
    # def memento_path(self, path: Path):
    #     self.compressor_specs['memento_path'] = str(path.absolute())

    # Tile Specs
    @property
    def datatype(self) -> str:
        return self.tile_specs['data_type']

    @datatype.setter
    def datatype(self, numpy_datatype: str):
        self.tile_specs['data_type'] = numpy_datatype

    # File Transfer Specs
    @property
    def ftp(self) -> str:
        return self.file_transfer_specs['protocol']

    @ftp.setter
    def ftp(self, protocol: str):
        self.file_transfer_specs['protocol'] = protocol

    @property
    def ftp_flags(self) -> str:
        return self.file_transfer_specs['protocol_flags']

    @ftp_flags.setter
    def ftp_flags(self, flags: str):
        self.file_transfer_specs['protocol_flags'] = flags

    # Daq Specs
    @property
    def daq_sample_rate(self):
        return self.daq_obj_kwds['samples_per_sec']

    @daq_sample_rate.setter
    def daq_sample_rate(self, hz: int):
        self.daq_obj_kwds['samples_per_sec'] = hz

    @property
    def n2c(self) -> dict:
        """dictionary {<analog output name> : <analog output channel>}."""
        return self.daq_obj_kwds['ao_channels']

    # Dynamically generated keyword arguments.
    @property
    def daq_obj_kwds(self):
        # Don't affect the config file's version by making a copy.
        obj_kwds = copy.deepcopy(self.cfg['daq_driver_kwds'])
        obj_kwds['period_time_s'] = sum([self.get_channel_cycle_time(ch)
                                         for ch in self.channels])
        return obj_kwds

    # Derived properties. These do not have setters
    @property
    def daq_period_time(self):
        return sum([self.get_channel_cycle_time(ch) for ch in self.channels])

    @property
    def camera_exposure_time(self):
        """Camera exposure time in seconds."""
        # (line interval [us]) * (number of rows [pixels]) * (1 [s] / 1e6 [us])
        return self.camera_line_interval_us * self.sensor_row_count / 1.0e6

    @property
    def camera_dwell_time(self):
        """The time in seconds that a given row is exposed to the laser."""
        # FIXME: this could be removed if derive the calculation from
        #   slit width in the waveform_generator.
        # (dwell time [us]) / (line interval [us/pixel]) is slit width.
        # (slit width [pixels]) * (line interval [us/pixel]) * (1 [s]/1e6[us])
        return self.slit_width * self.camera_line_interval_us / 1.0e6

    def sanity_check(self):
        error_msgs = []
        try:
            super().sanity_check()
        except AssertionError as e:
            error_msgs.append(str(e))
        # Proceed through ExaSPIM-specific checks:
        # Check that slit width >0 but less than the camera's number of rows.
        if self.slit_width <= 0 or self.slit_width > self.sensor_row_count:
            msg = f"Slit width must be greater than zero but less than or " \
                  f"equal to the number of rows ({self.sensor_row_count})."
            self.log.error(msg)
            error_msgs.append(msg)
        # Check that backlash reset distance > 0.
        if self.stage_backlash_reset_dist_um < 0:
            msg = f"Stage backlash reset distance " \
                  f"({self.stage_backlash_reset_dist_um} [um] must be greater" \
                  f"than 0."
            self.log.error(msg)
            error_msgs.append(msg)

        # TODO: Check that axis mapping has no repeat values.
        # TODO: Check that waveform specs are > 0.
        # TODO: Check that image stack chunk size is a multiple of 2

        # Create a big error message at the end.
        if error_msgs:
            all_msgs = "\n".join(error_msgs)
            raise AssertionError(all_msgs)

