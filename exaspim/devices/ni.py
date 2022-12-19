import nidaqmx
from nidaqmx.constants import FrequencyUnits as Freq
from nidaqmx.constants import Level
from nidaqmx.constants import AcquisitionType as AcqType
from nidaqmx.constants import Edge
from nidaqmx.constants import Slope


class NI:

    def __init__(self, dev_name: str, samples_per_sec: float,
                 period_time_s: float, ao_channels: dict):
        """init.

        :param dev_name: NI device name as it appears in Device Manager.
        :param samples_per_sec: sample playback rate in samples per second.
        :param period_time_s: the total waveform period for one frame pattern.
        :param ao_channels: dict in the form of
            {<analog output name>: <analog output channel>}.
        """
        self.dev_name = dev_name
        self.samples_per_sec = samples_per_sec
        self.period_time_s = period_time_s
        self.ao_names_to_channels = ao_channels
        # Total samples is the sum of the samples for every used laser channel.
        self.daq_samples = round(self.samples_per_sec * self.period_time_s)
        self.co_task = None
        self.ao_task = None

    def configure(self, frame_count: int = None, live: bool = False):
        """Configure the NI card to play either `frame_count` frames or
        continuously.

        :param frame_count: the number of frames to play waveforms for. If
            left unspecified, `live` must be true.
        :param live: if True, play the waveforms indefinitely. `frame_count`
            must be left unspecified in this case. Otherwise, play the
            waveforms for the specified `frame_count`.
        """
        # TODO: how do we generate multiple pulses for multichannel images?
        self.co_task = nidaqmx.Task('counter_output_task')
        co_chan = self.co_task.co_channels.add_co_pulse_chan_freq(
            f'/{self.dev_name}/ctr0',
            units=Freq.HZ,
            idle_state=Level.LOW,
            initial_delay=0.0,
            freq=self.samples_per_sec/self.daq_samples,
            duty_cycle=0.5)
        co_chan.co_pulse_term = f'/{self.dev_name}/PFI0'

        self.co_task.timing.cfg_implicit_timing(
            sample_mode=AcqType.CONTINUOUS if live else AcqType.FINITE,
            samps_per_chan=frame_count)

        self.ao_task = nidaqmx.Task("analog_output_task")
        for channel_name, channel_index in self.ao_names_to_channels.items():
            physical_name = f"/{self.dev_name}/ao{channel_index}"
            self.ao_task.ao_channels.add_ao_voltage_chan(physical_name)
        self.ao_task.timing.cfg_samp_clk_timing(
            rate=self.samples_per_sec,
            active_edge=Edge.RISING,
            sample_mode=AcqType.FINITE,
            samps_per_chan=self.daq_samples)
        self.ao_task.triggers.start_trigger.retriggerable = True
        # TODO: trigger source should be in the config.
        self.ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
#			trigger_source=f'/{self.dev_name}/PFI1',
            trigger_source=f'/{self.dev_name}/PFI0',
            trigger_edge=Slope.RISING)

    def assign_waveforms(self, voltages_t):
        self.ao_task.write(voltages_t)

    def start(self):
        if self.ao_task:
            self.ao_task.start()
        # time.sleep(2*(self.daq_samples/self.update_freq)) # wait for last AO to play
        # print(2*(self.daq_samples/self.update_freq))
        if self.co_task:
            self.co_task.start()

    def stop(self):
        if self.co_task:
            self.co_task.stop()
        # time.sleep(2*(self.daq_samples/self.update_freq)) # wait for last AO to play
        # print(2*(self.daq_samples/self.update_freq))
        if self.ao_task:
            self.ao_task.stop()

    def close(self):
        if self.co_task:
            self.co_task.close()
        if self.ao_task:
            self.ao_task.close()

