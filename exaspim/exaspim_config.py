import datetime
from math import ceil
from pathlib import Path
from mesospim.config_base import SpimConfig

# A template from which we can define a blank exaspim config.
# TODO: create this.
TomlTemplate = {}


class ExaspimConfig(SpimConfig):

    def __init__(self, toml_filepath: str):
        super().__init__(toml_filepath, TomlTemplate)

        # Make references to mutable objects
        self.stage_specs = self.cfg['sample_stage_specs']  # TODO: put in base class?
        self.channel_specs = self.cfg['channel_specs']

        # um per pixel
        #self.pixel_x = 0.748  # unit: um/px. x_voxel_size_um. Derived.
        #self.pixel_y = 0.748  # unit: um/px. y_voxel_size_um. Derived.
        self.pixel_z = 1.0                                      # unit: um/px

        self.channel_powers = {
                            '405': 0.0,
                            '488': 0.0,
                            '561': 0.0,
                            '638': 0.0
                        }
        self.n_channels = len(self.channels)
                        
        # viewer settings
        self.autoscale = False        # viewer: autoscaling bool
        self.method = 'Full'          # viewer: downscaling method
        self.frame_rate = 4           # viewer: framerate
        #self.scale_x = self.pixel_x  # viewer: scaling unit for pixels -> renderer seems to default to pyramid position 2
        #self.scale_y = self.pixel_y  # viewer: scaling unit for pixels

        # camera settings
        #self.cam_x = 14192           # unit: pixels
        #self.cam_y = 10640           # unit: pixels
        self.ram_buffer = 8           # unit: frames
        self.dwell_time = 5.0/1000.0  # unit: s
        self.digital_gain = 1         # unit: ADU

        # data writer settings
        self.n_threads = 32 # threads
        self.compression = 'lz4'      # writer: compression method
        #self.chunk_size = 128         # unit: frames


        # rotation stage settings
        self.rotation =             40.5                        # unit: degrees

        # waveform generator settings
        self.dev_name = 'Dev1'                                  # waveform enerator: address
        self.rate = 1e4                                         # unit: Hz

        self.camera_exposure_time = 15/1000*10640/1000.0        # unit: ms
        self.rest_time =            50.0/1000.0                 # unit: ms
        self.pulse_time =           10.0/1000.0                 # unit: ms
        self.n2c =                  {
                                        'etl': 0,
                                        'camera': 1,
                                        'stage': 2,
                                        '488': 3,
                                        '638': 4,
                                        '561': 5,
                                        '405': 6
                                    }
        # tiling settings
        #self.y_grid_step_um = \
        #    (1 - self.tile_overlap_x_percent/100.0) * self.cam_x*self.pixel_x
        #
        #self.z_grid_step_um = \
        #    (1 - self.z_overlap/100.0) * self.cam_y*self.pixel_y

        # Note: these are no longer accurate because we did axis remapping.
        #self.y_tiles = ceil(self.volume_y_um/self.y_grid_step_um)
        #self.z_tiles = ceil(self.volume_z_um/self.z_grid_step_um)
        #self.n_frames = int(self.volume_x_um/self.pixel_z)      # unit: frames

    def get_channel_cycle_time(self, wavelength: int):
        """Returns required time to play a waveform period for a given channel."""
        return self.camera_exposure_time \
               + self.get_etl_buffer_time(wavelength) \
               + self.rest_time

    def get_camera_delay_time(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['camera']['delay_time_s']

    def get_etl_amplitude(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['amplitude']

    def get_etl_offset(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['offset']

    def get_etl_nonlinear(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['nonlinear']

    def get_etl_interp_time(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['interp_time_s']

    def get_etl_buffer_time(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['etl']['buffer_time_s']

    def get_laser_buffer_time(self, wavelength: int):
        return self.channel_specs[str(wavelength)]['buffer_time_s']

    # TODO: add setters for the above.

    @property
    def z_step_size_um(self):
        return self.cfg['imaging_specs']['z_step_size_um']

    @z_step_size_um.setter
    def z_step_size_um(self, um: float):
        self.cfg['imaging_specs']['z_step_size_um'] = um
        
    @property
    def stage_backlash_reset_dist_um(self):
        return self.stage_specs['backlash_reset_distance_um']

    @stage_backlash_reset_dist_um.setter
    def stage_backlash_reset_dist_um(self, micrometers: int):
        self.stage_specs['backlash_reset_distance_um'] = micrometers

    @property
    def compressor_style(self):
        return self.design_specs['compression_style']

    @property
    def compressor_thread_count(self):
        return self.design_specs['compressor_thread_count']

    @property
    def compressor_chunk_size(self):
        """number of images in a chunk to be compressed at a time."""
        return self.design_specs['image_stack_chunk_size']

    # @properties for flattening object hierarchy
    @property
    def datatype(self) -> str:
        return self.tile_specs['data_type']

    @datatype.setter
    def datatype(self, numpy_datatype: str):
        self.tile_specs['data_type'] = numpy_datatype

    @property
    def memento_path(self) -> Path:
        return Path(self.design_specs['memento_executable_path'])

    @memento_path.setter
    def memento_path(self, path: Path):
        self.design_specs['memento_path'] = str(path.absolute())

    @property
    def ftp(self) -> str:
        return self.design_specs['file_transfer_protocol']

    @ftp.setter
    def ftp(self, protocol: str):
        self.design_specs['file_transfer_protocol'] = protocol

    @property
    def ftp_flags(self) -> str:
        return self.design_specs['file_transfer_protocol_flags']

    @ftp_flags.setter
    def ftp_flags(self, flags: str):
        self.design_specs['file_transfer_protocol_flags'] = flags
        
    @property
    def daq_update_freq(self):
        return self.daq_obj_kwds['update_frequency_hz']

    @daq_update_freq.setter
    def daq_update_freq(self, hz: int):
        self.daq_obj_kwds['update_frequency_hz'] = hz

    # Keywords
    @property
    def tiger_obj_kwds(self):
        return self.cfg['tiger_controller_driver_kwds']

    @property
    def sample_pose_kwds(self):
        return self.cfg['sample_pose_kwds']

    # Derived properties
    @property
    def daq_num_samples(self):
        """Total samples for waveform generation."""
        samples = 0
        for ch in self.channels:
            samples += self.rate * self.get_channel_cycle_time(ch)
        return round(samples)
