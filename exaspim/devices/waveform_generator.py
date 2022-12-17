import nidaqmx
import numpy as np
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
    axes.legend(loc="upper right")
    fig.savefig("plot.pdf")


def generate_waveforms(cfg, plot=False):
    voltages_t = {}
    total_samples = 0
    for ch in cfg.channels:
        # Create samples arrays for various relevant timings
        camera_exposure_samples = int(cfg.daq_sample_rate * cfg.camera_exposure_time)
        camera_delay_samples = int(cfg.daq_sample_rate * cfg.get_camera_delay_time(ch))
        etl_buffer_samples = int(cfg.daq_sample_rate * cfg.get_etl_buffer_time(ch))
        laser_buffer_samples = int(cfg.daq_sample_rate * cfg.get_laser_buffer_time(ch))
        rest_samples = int(cfg.daq_sample_rate * cfg.frame_rest_time)
        dwell_time_samples = int(cfg.daq_sample_rate * cfg.camera_dwell_time)
        pulse_samples = int(cfg.daq_sample_rate * cfg.ttl_pulse_time)
        channel_samples = camera_exposure_samples + etl_buffer_samples + rest_samples

        total_samples += channel_samples

        voltages_t[ch] = np.zeros((len(cfg.n2c), channel_samples))

        # Generate ETL signal
        t_etl = np.linspace(0, cfg.camera_exposure_time + cfg.get_etl_buffer_time(ch),
                            camera_exposure_samples + etl_buffer_samples, endpoint=False)
        voltages_etl = -cfg.get_etl_amplitude(ch) * signal.sawtooth(
            2 * np.pi / (cfg.camera_exposure_time + cfg.get_etl_buffer_time(ch)) * t_etl, width=1.0) + cfg.get_etl_offset(ch)
        t0 = t_etl[0]
        t1 = t_etl[int((camera_exposure_samples + etl_buffer_samples) * cfg.get_etl_interp_time(ch))]
        tf = t_etl[-1]
        v0 = voltages_etl[0]
        v1 = voltages_etl[int((camera_exposure_samples + etl_buffer_samples) * cfg.get_etl_interp_time(ch))] + cfg.get_etl_nonlinear(ch)
        vf = voltages_etl[-1]
        f = interpolate.interp1d([t0, t1, tf], [v0, v1, vf], kind='quadratic')
        voltages_etl = f(t_etl)

        voltages_t[ch][cfg.n2c['etl'], 0:camera_exposure_samples + etl_buffer_samples] = voltages_etl  # write in ETL sawtooth
        voltages_t[ch][cfg.n2c['etl'], camera_exposure_samples + etl_buffer_samples::] = cfg.get_etl_offset(ch) + cfg.get_etl_amplitude(ch)  # snap back ETL after sawtooth
        voltages_t[ch][cfg.n2c['etl'],
        camera_exposure_samples + etl_buffer_samples:camera_exposure_samples + etl_buffer_samples + dwell_time_samples] = \
            cfg.get_etl_offset(ch) - cfg.get_etl_amplitude(ch)  # delay snapback until last row is done exposing

        # Generate camera TTL signal
        voltages_t[ch][cfg.n2c['camera'], int(etl_buffer_samples / 2.0) + camera_delay_samples:int(
            etl_buffer_samples / 2.0) + camera_delay_samples + pulse_samples] = 5.0

        # Generate laser TTL signal
        voltages_t[ch][cfg.n2c[str(ch)],  # FIXME: remove n2c or move it into the config.
        int(etl_buffer_samples / 2.0) - laser_buffer_samples + camera_delay_samples:int(
            etl_buffer_samples / 2.0) + camera_exposure_samples + dwell_time_samples + camera_delay_samples] = 5.0

        # Generate stage TTL signal
        if ch == cfg.channels[-1]:
            voltages_t[ch][cfg.n2c['stage'],
            camera_exposure_samples + etl_buffer_samples + dwell_time_samples:camera_exposure_samples + etl_buffer_samples + dwell_time_samples + pulse_samples] = 0.0

    # Merge voltage arrays
    voltages_out = np.array([]).reshape((len(cfg.n2c), 0))
    for ch in cfg.channels:
        voltages_out = np.hstack((voltages_out, voltages_t[ch]))

    if plot:
        # Total waveform time in sec.
        t = np.linspace(0, cfg.daq_period_time, total_samples, endpoint=False)
        plot_waveforms_to_pdf(t, voltages_out)

    return voltages_out


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

