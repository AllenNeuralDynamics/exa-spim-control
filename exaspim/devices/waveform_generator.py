import nidaqmx
import time
import numpy
import matplotlib.pyplot as plt
from nidaqmx.constants import FrequencyUnits as Freq
from nidaqmx.constants import Level
from nidaqmx.constants import AcquisitionType as AcqType
from nidaqmx.constants import Edge
from nidaqmx.constants import Slope
from scipy import signal
from scipy import interpolate


def plot_waveforms_to_pdf(t, voltages_t):
	etl_t, camera_enable_t, stage_enable_t, laser_488_enable_t, laser_638_enable_t, laser_561_enable_t, laser_405_enable_t = voltages_t  # TODO fix this, use AO names to channel number to autopopulate

	fig, axes = plt.subplots(nrows=1, ncols=1, figsize=(10, 7))
	axes.set_title("One Frame.")
	axes.plot(t, etl_t, label="etl")
	axes.plot(t, laser_488_enable_t, label="laser enable")
	axes.plot(t, laser_561_enable_t, label="laser enable")
	axes.plot(t, laser_638_enable_t, label="laser enable")
	axes.plot(t, laser_405_enable_t, label="laser enable")
	axes.plot(t, camera_enable_t, label="camera enable")
	axes.plot(t, stage_enable_t, label="stage_enable")
	axes.set_xlabel("time [s]")
	axes.set_ylabel("amplitude [V]")
	axes.set_ylim(0, 5)
	axes.legend(loc="center")
	fig.savefig("plot.pdf")


def generate_waveforms(cfg, plot=False):
	voltages_t = {}
	for ch in cfg.channels:
		# Create samples arrays for various relevant timings
		camera_exposure_samples = int(cfg.rate * cfg.camera_exposure_time)
		camera_delay_samples = int(cfg.rate * cfg.camera_delay_time[ch])
		etl_buffer_samples = int(cfg.rate * cfg.etl_buffer_time[ch])
		laser_buffer_samples = int(cfg.rate * cfg.laser_buffer_time[ch])
		rest_samples = int(cfg.rate * cfg.rest_time)
		dwell_time_samples = int(cfg.rate * cfg.dwell_time)
		pulse_samples = int(cfg.rate * cfg.pulse_time)
		total_samples = camera_exposure_samples + etl_buffer_samples + rest_samples

		voltages_t[ch] = numpy.zeros((len(cfg.n2c), total_samples))  # TODO fix this from being hardcoded to 4

		# Generate ETL signal
		t_etl = numpy.linspace(0, cfg.camera_exposure_time + cfg.etl_buffer_time[ch],
							   camera_exposure_samples + etl_buffer_samples, endpoint=False)
		voltages_etl = -cfg.etl_amplitude[ch] * signal.sawtooth(
			2 * numpy.pi / (cfg.camera_exposure_time + cfg.etl_buffer_time[ch]) * t_etl, width=1.0) + cfg.etl_offset[ch]
		t0 = t_etl[0]
		t1 = t_etl[int((camera_exposure_samples + etl_buffer_samples) * cfg.etl_interp_time[ch])]
		tf = t_etl[-1]
		v0 = voltages_etl[0]
		v1 = voltages_etl[int((camera_exposure_samples + etl_buffer_samples) * cfg.etl_interp_time[ch])] + cfg.etl_nonlinear[ch]
		vf = voltages_etl[-1]
		f = interpolate.interp1d([t0, t1, tf], [v0, v1, vf], kind='quadratic')
		voltages_etl = f(t_etl)

		voltages_t[ch][cfg.n2c['etl'],
		0:camera_exposure_samples + etl_buffer_samples] = voltages_etl  # write in ETL sawtooth
		voltages_t[ch][cfg.n2c['etl'], camera_exposure_samples + etl_buffer_samples::] = cfg.etl_offset[ch] + cfg.etl_amplitude[ch]  # snap back ETL after sawtooth
		voltages_t[ch][cfg.n2c['etl'],
		camera_exposure_samples + etl_buffer_samples:camera_exposure_samples + etl_buffer_samples + dwell_time_samples] = \
			cfg.etl_offset[ch] - cfg.etl_amplitude[ch]  # delay snapback until last row is done exposing

		# Generate camera TTL signal
		voltages_t[ch][cfg.n2c['camera'], int(etl_buffer_samples / 2.0) + camera_delay_samples:int(
			etl_buffer_samples / 2.0) + camera_delay_samples + pulse_samples] = 5.0

		# Generate laser TTL signal
		voltages_t[ch][cfg.n2c[ch],
		int(etl_buffer_samples / 2.0) - laser_buffer_samples + camera_delay_samples:int(
			etl_buffer_samples / 2.0) + camera_exposure_samples + dwell_time_samples + camera_delay_samples] = 5.0

		# Generate stage TTL signal
		if ch == cfg.channels[-1]:
			voltages_t[ch][cfg.n2c['stage'],
			camera_exposure_samples + etl_buffer_samples + dwell_time_samples:camera_exposure_samples + etl_buffer_samples + dwell_time_samples + pulse_samples] = 0.0

	# Merge voltage arrays
	voltages_out = numpy.array([]).reshape((len(cfg.n2c), 0))
	for ch in cfg.channels:
		voltages_out = numpy.hstack((voltages_out, voltages_t[ch]))

	if plot:
		# Total waveform time in sec
		# FIXME
		t = numpy.linspace(0, (cfg.daq_num_samples / cfg.rate), cfg.daq_num_samples, endpoint=False)
		plot_waveforms_to_pdf(t, voltages_out)

	return voltages_out


class NI:

	def __init__(self):

		self.co_task = None
		self.ao_task = None
		self.daq_samples = 0

	# TODO: separate cfg dependency. Pass everything in here as a parameter.
	def configure(self, cfg, live=False):
		self.cfg = cfg

		# total samples is the sum of the samples for every used laser channel.
		samples = 0
		for ch in self.cfg.channels:
			samples += self.cfg.rate*self.cfg.get_channel_cycle_time(ch)
		self.daq_samples = round(samples)

		self.co_task = nidaqmx.Task('counter_output_task')
		self.co_task.co_channels.add_co_pulse_chan_freq(
			'/Dev1/ctr0',
			units=Freq.HZ,
			idle_state=Level.LOW,
			initial_delay=0.0,
			freq=1.0/(self.daq_samples/self.cfg.rate),
			duty_cycle=0.5)
		
		self.co_task.timing.cfg_implicit_timing(
			sample_mode=AcqType.CONTINUOUS if live else AcqType.FINITE,
			samps_per_chan=self.cfg.n_frames)

		# TODO: this should be in the config.
		self.co_task.co_pulse_term = '/Dev1/PFI0'

		self.ao_task = nidaqmx.Task("analog_output_task")
		for channel_name, channel_index in self.cfg.n2c.items():
			physical_name = f"/{self.cfg.dev_name}/ao{channel_index}"
			self.ao_task.ao_channels.add_ao_voltage_chan(physical_name)
		self.ao_task.timing.cfg_samp_clk_timing(
			rate=self.cfg.rate,
			active_edge=Edge.RISING,
			sample_mode=AcqType.FINITE,
			samps_per_chan=self.daq_samples)
		self.ao_task.triggers.start_trigger.retriggerable = True
		# TODO: trigger source should be in the config.
		self.ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
			trigger_source='/Dev1/PFI1',
			trigger_edge=Slope.RISING)

		voltages_out = generate_waveforms(self.cfg)
		self.ao_task.write(voltages_out)

	def start(self):
		if self.ao_task:
			self.ao_task.start()
		# time.sleep(2*(self.daq_samples/self.cfg.rate)) # wait for last AO to play
		# print(2*(self.daq_samples/self.cfg.rate))
		if self.co_task:
			self.co_task.start()

	def stop(self):
		if self.co_task:
			self.co_task.stop()
		# time.sleep(2*(self.daq_samples/self.cfg.rate)) # wait for last AO to play
		# print(2*(self.daq_samples/self.cfg.rate))
		if self.ao_task:
			self.ao_task.stop()

	def close(self):
		if self.co_task:
			self.co_task.close()
		if self.ao_task:
			self.ao_task.close()

