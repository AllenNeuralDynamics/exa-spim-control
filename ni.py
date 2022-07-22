"""
NIDAQMX setup for timing/triggering using PCIe-6738 card.

"""

import nidaqmx
import time
import numpy
from nidaqmx import constants
from numpy import ndarray

class WaveformGeneratorHardware:

	def __init__(self, devName, rate, period, n_frames, ao_names_to_channels):

		self.devName = devName 	# NI card address, i.e. Dev2
		self.rate = rate 	# NI sampling rate, i.e. 1e3
		self.period = period # frame time period
		self.n_frames = n_frames # number of frames
		self.ao_names_to_channels = ao_names_to_channels # TODO. use the lookup table of channel names to abstract away how they map to numbered AO channels
		self.num_channels = len(self.ao_names_to_channels)
		self.ao_task = None

	def configure(self):

		sample_count = round(self.rate*self.period)  # Digital samples based on rate/time

		self.co_task = nidaqmx.Task('counter_output_task')
		self.co_task.co_channels.add_co_pulse_chan_freq('/Dev1/ctr0', units = nidaqmx.constants.FrequencyUnits.HZ, idle_state = nidaqmx.constants.Level.LOW,  initial_delay = 0.0, freq = 1.0/self.period, duty_cycle = 0.5)
		self.co_task.timing.cfg_implicit_timing(sample_mode = nidaqmx.constants.AcquisitionType.FINITE, samps_per_chan = self.n_frames)
		self.co_task.co_pulse_term = '/Dev1/PFI0'

		self.ao_task = nidaqmx.Task("analog_output_task")
		for channel_name, channel_index in self.ao_names_to_channels.items():
			physical_name = f"/{self.devName}/ao{channel_index}"
			self.ao_task.ao_channels.add_ao_voltage_chan(physical_name)
		self.ao_task.timing.cfg_samp_clk_timing(rate=1e4,
												active_edge=nidaqmx.constants.Edge.RISING,
												sample_mode=nidaqmx.constants.AcquisitionType.FINITE,
												samps_per_chan=sample_count)
		self.ao_task.triggers.start_trigger.retriggerable = True
		self.ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(trigger_source = '/Dev1/PFI1', trigger_edge = nidaqmx.constants.Slope.RISING)

	def assign_waveforms(self, voltages_t):
		"""Write analog and digital waveforms to device."""
		self.ao_task.write(voltages_t)  # arrays of floats

	def start(self):
		"""start tasks."""
		if self.ao_task:
			self.ao_task.start()
		if self.co_task:
			self.co_task.start()

	def stop(self):
		"""Stop the tasks"""
		if self.co_task:
			self.co_task.stop()
		time.sleep(self.period)
		if self.ao_task:
			self.ao_task.stop()

	def close(self):
		"""Close the tasks."""
		if self.co_task:
			self.co_task.close()
		if self.ao_task:
			self.ao_task.close()
