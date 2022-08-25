import datetime
from math import ceil

class config():

    def __init__(self):

        # scan settings
        date_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.source_path = 'D:\\'                               # local storage path
        self.destination_path = 'X:\\'                          # network storage path
        self.source_path = self.source_path + date_time + '\\'
        self.destination_path = self.destination_path + date_time + '\\'
        self.filename = 'tile'                                  # base filename

        self.datatype = 'uint16'                                # unit: bits
        self.y_overlap = 15                                     # unit: percent
        self.z_overlap = 15                                     # unit: percent
        # self.volume_x_um = 12000                              # unit: um
        # self.volume_y_um = 32000                              # unit: um
        # self.volume_z_um = 15000                              # unit: um
        self.volume_x_um = 12000                                # unit: um
        self.volume_y_um = 32000                                # unit: um
        self.volume_z_um = 15000                                # unit: um
        self.pixel_x = 0.748                                    # unit: um/px
        self.pixel_y = 0.748                                    # unit: um/px
        self.pixel_z = 1.0                                      # unit: um/px
        self.channels = [
                            '488',
                            '561'
                        ]
        self.channel_powers = {
                            '405': 0.0,
                            '488': 0.0,
                            '561': 0.0,
                            '638': 0.0
                        }
        self.n_channels = len(self.channels)
                        
        # viewer settings
        self.autoscale = False                                   # viewer: autoscaling bool
        self.method = 'Full'                                    # viewer: downscaling method
        self.frame_rate = 4                                     # viewer: framerate
        self.scale_x = self.pixel_x                             # viewer: scaling unit for pixels -> renderer seems to default to pyramid position 2
        self.scale_y = self.pixel_y                             # viewer: scaling unit for pixels

        # camera settings
        self.cam_x = 14192                                      # unit: pixels
        self.cam_y = 10640                                      # unit: pixels
        self.ram_buffer = 8                                     # unit: frames
        self.dwell_time = 5.0/1000.0                            # unit: s
        self.digital_gain = 1                                   # unit: ADU

        # memento logger settings
        self.memento_path = "C:\\Program Files\\Euresys\\Memento\\bin\\x86_64\\memento.exe"

        # data writer settings
        self.n_threads = 32 # threads
        self.compression = 'lz4'                                # writer: compression method
        self.chunk_size = 128                                   # unit: frames

        # file transfer settings
        self.ftp = 'xcopy'                                      # file transfer: protocol
        self.ftp_flags = '/j /i'                                # file transfer: flags

        # rotation stage settings
        self.rotation =             40.5                        # unit: degrees

        # waveform generator settings
        self.dev_name = 'Dev1'                                  # waveform enerator: address
        self.rate = 1e4                                         # unit: Hz
        self.etl_amplitude =        {
                                        '488': 0.171,
                                        '561': 0.171,
                                        '638': 0.171
                                    }
        self.etl_offset =           {
                                        '488': 2.422,
                                        '561': 2.422,
                                        '638': 2.422
                                    }
        self.etl_nonlinear =        {
                                        '488': -0.007,
                                        '561': -0.007,
                                        '638': -0.007
                                    }
        self.etl_interp_time =      {
                                        '488': 0.5,
                                        '561': 0.5,
                                        '638': 0.5
                                    }

        self.camera_delay_time =    {
                                        '488': 0.0/1000.0,
                                        '561': 0.0/1000.0,
                                        '638': 0.0/1000.0
                                    }
        self.etl_buffer_time =      {
                                        '488': 50.0/1000.0,
                                        '561': 50.0/1000.0,
                                        '638': 50.0/1000.0
                                    }
        self.laser_buffer_time =    {
                                        '488': 1.0/1000.0,
                                        '561': 1.0/1000.0,
                                        '638': 1.0/1000.0
                                    }

        self.camera_exposure_time = 15/1000*10640/1000.0        # unit: ms
        self.rest_time =            50.0/1000.0                 # unit: ms
        self.pulse_time =           10.0/1000.0                 # unit: ms
        
        self.total_time =           {   '488': self.camera_exposure_time + self.etl_buffer_time['488'] + self.rest_time,
                                        '561': self.camera_exposure_time + self.etl_buffer_time['561'] + self.rest_time,
                                        '638': self.camera_exposure_time + self.etl_buffer_time['638'] + self.rest_time 
                                    }
        
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
        self.y_grid_step_um = \
            (1 - self.y_overlap/100.0) * self.cam_x*self.pixel_x
        
        self.z_grid_step_um = \
            (1 - self.z_overlap/100.0) * self.cam_y*self.pixel_y     

        self.y_tiles = ceil(self.volume_y_um/self.y_grid_step_um)

        self.z_tiles = ceil(self.volume_z_um/self.z_grid_step_um)

        self.n_frames = int(self.volume_x_um/self.pixel_z)      # unit: frames