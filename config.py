import datetime

class config():

    def __init__(self):

        # scan settings
        self.source_path = 'D:\\'                               # local storage path
        self.destination_path = 'X:\\'                          # network storage path
        date_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.source_path = self.source_path + date_time + '\\'
        self.destination_path = self.destination_path + date_time + '\\'
        self.filename = 'tile'                                  # base filename
        self.datatype = 'uint16'                                # unit: bits
        self.n_frames = 1000                                    # unit: frames
        self.x_tiles = 3                                        # unit: tiles
        self.y_tiles = 3                                        # unit: tiles
        self.x_overlap = 15                                     # unit: percent
        self.y_overlap = 15                                     # unit: percent
        self.pixel_x = 0.748                                    # unit: um/px
        self.pixel_y = 0.748                                    # unit: um/px
        self.pixel_z = 1.0                                      # unit: um/px
        self.channels = [
                            '405',
                            '488'
                        ]
        self.channel_powers = {
                            '405': 0.0,
                            '488': 0.0,
                            '561': 0.0,
                            '638': 0.0
                        }
        self.n_channels = len(self.channels)
                        
        # viewer settings
        self.autoscale = True                                   # viewer: autoscaling bool
        self.method = 'Center'                                  # viewer: downscaling method
        self.frame_rate = 4                                     # viewer: framerate
        self.scale_x = self.pixel_x*8                           # viewer: scaling unit for pixels
        self.scale_y = self.pixel_y*8                           # viewer: scaling unit for pixels

        # camera settings
        self.cam_x = 14192                                      # unit: pixels
        self.cam_y = 10640                                      # unit: pixels
        self.ram_buffer = 8                                     # unit: frames
        self.dwell_time = 5.0                                   # unit: ms
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

        # waveform generator settings
        self.dev_name = 'Dev1'                                  # waveform enerator: address
        self.rate = 1e4                                         # unit: Hz
        self.etl_amplitude = 0.30/2.0                           # unit: volts
        self.etl_offset = 2.27 + self.etl_amplitude             # unit: volts
        self.etl_nonlinear = -0.005                             # unit: volts
        self.etl_interp_time = 0.5                              # unit: percent
        self.camera_exposure_time = 15/1000*10640               # unit: ms
        self.camera_delay_time = 1.0                            # unit: ms
        self.etl_buffer_time = 25.0                             # unit: ms
        self.laser_buffer_time = 1.0                            # unit: ms
        self.rest_time = 50.0                                   # unit: ms
        self.line_time = 5.0                                    # unit: ms (dwell time)
        self.pulse_time = 10.0                                  # unit: ms
        self.total_time = self.camera_exposure_time + self.etl_buffer_time + self.rest_time # unit: ms
        self.ao_names_to_channels = {
                                        'etl': 0,
                                        'camera': 1,
                                        'stage': 2,
                                        'laser': 3
                                    }