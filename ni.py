"""
NIDAQMX setup for timing/triggering using PCIe-6738 card.

"""

import nidaqmx
from nidaqmx import constants
from numpy import ndarray


class WaveformGeneratorHardware:

	def __init__(self, devName, rate, period, ao_names_to_channels):

		self.devName = devName 	# NI card address, i.e. Dev2
		self.rate = rate 	# NI sampling rate, i.e. 1e3
		self.period = period
		self.ao_names_to_channels = ao_names_to_channels # TODO. use the lookup table of channel names to abstract away how they map to numbered AO channels
		self.num_channels = len(self.ao_names_to_channels)
		self.ao_task = None

	def configure(self):

		sample_count = round(self.rate*self.period)  # Digital samples based on rate/time

		# Configure analog output task. Set triggering to the start of digital output task. See:
		# https://www.ni.com/docs/en-US/bundle/ni-daqmx-21.3-help/page/mxcncpts/syncstarttrigger.html
		self.ao_task = nidaqmx.Task("analog_output_task")
		for channel_name, channel_index in self.ao_names_to_channels.items():
			physical_name = f"/{self.devName}/ao{channel_index}"
			self.ao_task.ao_channels.add_ao_voltage_chan(physical_name)
		self.ao_task.timing.cfg_samp_clk_timing(rate=self.rate,
												active_edge=nidaqmx.constants.Edge.RISING,
												sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
												samps_per_chan=sample_count)

	def assign_waveforms(self, voltages_t):
		"""Write analog and digital waveforms to device."""
		self.ao_task.write(voltages_t)  # arrays of floats

	def start(self):
		"""start tasks."""
		self.ao_task.start()

	def stop(self):
		"""Stop the tasks"""
		self.ao_task.stop()

	def close(self):
		"""Close the tasks."""
		if self.ao_task:
			self.ao_task.close()
