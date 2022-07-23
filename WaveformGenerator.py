import nidaqmx
import time
import numpy
import matplotlib.pyplot as plt
from scipy import signal

class WaveformGenerator(object):

	def __init__(self):

		self.devName = 'Dev1' 	# NI card address, i.e. Dev2
		self.rate = 1e4 	# NI sampling rate, i.e. 1e3
		self.period = 260/1000 # frame time period
		self.n_frames = 500 # number of frames
		self.ao_names_to_channels = ao_channels =   {'etl': 0, # TODO. use the lookup table of channel names to abstract away how they map to numbered AO channels
													 'camera': 1,
													 'stage': 2,
													 'laser': 3
													}
		self.num_channels = len(self.ao_names_to_channels)

		self.rate = 1e4
		self.etl_amplitude = 0.35/2.0 # volts
		self.etl_offset = 2.155 + self.etl_amplitude # volts
		self.camera_exposure_time = 15/1000*10640/1000 # sec
		self.camera_delay_time = 6.5/1000 # sec
		self.etl_buffer_time = 25.0/1000 # sec
		self.laser_buffer_time = 5.0/1000 # sec
		self.rest_time = 75.4/1000 # sec
		self.line_time = 5.0/1000 # sec
		self.pulse_time = 10.0/1000 # sec
		self.total_time = self.camera_exposure_time + self.etl_buffer_time + self.rest_time

		self.co_task = None
		self.ao_task = None

	def configure(self):

		self.co_task = nidaqmx.Task('counter_output_task')
		self.co_task.co_channels.add_co_pulse_chan_freq('/Dev1/ctr0', units = nidaqmx.constants.FrequencyUnits.HZ, idle_state = nidaqmx.constants.Level.LOW,  initial_delay = 0.0, freq = 1.0/self.period, duty_cycle = 0.5)
		self.co_task.timing.cfg_implicit_timing(sample_mode = nidaqmx.constants.AcquisitionType.FINITE, samps_per_chan = self.n_frames)
		self.co_task.co_pulse_term = '/Dev1/PFI0'

		self.ao_task = nidaqmx.Task("analog_output_task")
		for channel_name, channel_index in self.ao_names_to_channels.items():
			physical_name = f"/{self.devName}/ao{channel_index}"
			self.ao_task.ao_channels.add_ao_voltage_chan(physical_name)
		self.ao_task.timing.cfg_samp_clk_timing(rate=self.rate,
												active_edge=nidaqmx.constants.Edge.RISING,
												sample_mode=nidaqmx.constants.AcquisitionType.FINITE,
												samps_per_chan=int(self.rate*self.period))
		self.ao_task.triggers.start_trigger.retriggerable = True
		self.ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(trigger_source = '/Dev1/PFI1', trigger_edge = nidaqmx.constants.Slope.RISING)

	def generate_waveforms(self):

		# Create samples arrays for various relevant timings
		camera_exposure_samples = int(self.rate*self.camera_exposure_time)
		camera_delay_samples = int(self.rate*self.camera_delay_time)
		etl_buffer_samples = int(self.rate*self.etl_buffer_time)
		laser_buffer_samples = int(self.rate*self.laser_buffer_time)
		rest_samples = int(self.rate*self.rest_time)
		line_time_samples = int(self.rate*self.line_time)
		pulse_samples = int(self.rate*self.pulse_time)
		total_samples = camera_exposure_samples + etl_buffer_samples + rest_samples

		# Initialize 2D voltages array
		voltages_t = numpy.zeros((4, total_samples)) # TODO fix this from being hardcoded to 4

		# Generate ETL signal
		t_etl = numpy.linspace(0, self.camera_exposure_time + self.etl_buffer_time, camera_exposure_samples + etl_buffer_samples, endpoint = False)
		voltages_etl = -self.etl_amplitude*signal.sawtooth(2*numpy.pi/(self.camera_exposure_time + self.etl_buffer_time)*t_etl, width = 1.0) + self.etl_offset
		voltages_t[0, 0:camera_exposure_samples + etl_buffer_samples] = voltages_etl # write in ETL sawtooth
		voltages_t[0, camera_exposure_samples + etl_buffer_samples::] = self.etl_offset + self.etl_amplitude # snap back ETL after sawtooth
		voltages_t[0, camera_exposure_samples + etl_buffer_samples:camera_exposure_samples + etl_buffer_samples + line_time_samples] = self.etl_offset - self.etl_amplitude # delay snapback until last row is done exposing

		# Generate camera TTL signal
		voltages_t[1, int(etl_buffer_samples/2.0)+camera_delay_samples:int(etl_buffer_samples/2.0) + camera_delay_samples + pulse_samples] = 5.0

		# Generate stage TTL signal
		voltages_t[2, camera_exposure_samples + etl_buffer_samples + line_time_samples:camera_exposure_samples + etl_buffer_samples + line_time_samples + pulse_samples] = 5.0

		# Generate laser TTL signal
		voltages_t[3, int(etl_buffer_samples/2.0)-laser_buffer_samples:int(etl_buffer_samples/2.0) + camera_exposure_samples + line_time_samples] = 5.0

		# Total waveform time in sec
		t = numpy.linspace(0, self.total_time, total_samples, endpoint = False)

		self.ao_task.write(voltages_t)

		self.plot_waveforms_to_pdf(t, voltages_t)

	def start(self):

		if self.ao_task:
			self.ao_task.start()
		if self.co_task:
			self.co_task.start()

	def stop(self):

		if self.co_task:
			self.co_task.stop()
		time.sleep(self.period)
		if self.ao_task:
			self.ao_task.stop()

	def close(self):

		if self.co_task:
			self.co_task.close()
		if self.ao_task:
			self.ao_task.close()

	def plot_waveforms_to_pdf(self, t, voltages_t):

		etl_t, camera_enable_t, stage_enable_t, laser_enable_t = voltages_t # TODO fix this, use AO names to channel number to autopopulate

		fig, axes = plt.subplots(nrows=1, ncols=1, figsize=(10, 7))

		axes.set_title("One Frame.")
		axes.plot(t, etl_t, label="etl")
		axes.plot(t, laser_enable_t, label="laser enable")
		axes.plot(t, camera_enable_t, label="camera enable")
		axes.plot(t, stage_enable_t, label="stage_enable")
		axes.set_xlabel("time [s]")
		axes.set_ylabel("amplitude [V]")
		axes.legend(loc="center")

		fig.savefig("plot.pdf")
