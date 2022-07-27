class config():

    def __init__(self):

        # scan settings
        self.source_path = 'D:\\'                               # local storage path
        self.destination_path = 'X:\\'                          # network storage path
        self.filename = 'test'                                  # base filename
        self.datatype = 'uint16'                                # unit: bits
        self.n_tiles = 10                                       # unit: tiles
        self.pixel_x = 0.748                                    # unit: um/px
        self.pixel_y = 0.748                                    # unit: um/px
        self.pixel_z = 1.0                                      # unit: um/px
        self.channels = {
                            '405': False,
                            '488': False,
                            '561': False,
                            '648': False
                        }
        self.channel_powers = {
                            '405': 0.0,
                            '488': 0.0,
                            '561': 0.0,
                            '648': 0.0
                        }
                        
        # viewer settings
        self.autoscale = False                                  # viewer: autoscaling bool
        self.method = 'center'                                  # viewer: downscaling method
        self.frame_rate = 4                                     # unit: framerate

        # camera settings
        self.n_frames = 100000                                  # unit: frames
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
        self.period = 210                                       # unit: ms
        self.etl_amplitude = 0.35/2.0                           # unit: volts
        self.etl_offset = 2.155 + self.etl_amplitude            # unit: volts
        self.camera_exposure_time = 15/1000*10640               # unit: ms
        self.camera_delay_time = 6.5                            # unit: ms
        self.etl_buffer_time = 25.0                             # unit: ms
        self.laser_buffer_time = 5.0                            # unit: ms
        self.rest_time = 25.4                                   # unit: ms
        self.line_time = 5.0                                    # unit: ms (dwell time)
        self.pulse_time = 10.0                                  # unit: ms
        self.ao_names_to_channels = {
                                        'etl': 0,
                                        'camera': 1,
                                        'stage': 2,
                                        'laser': 3
                                    }