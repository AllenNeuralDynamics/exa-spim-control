import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy import interpolate


def plot_waveforms_to_pdf(t, voltages_t):
    etl_t, camera_enable_t, stage_enable_t, laser_488_enable_t, laser_638_enable_t, laser_561_enable_t, laser_405_enable_t, galvo_a_t, galvo_b_t = voltages_t  # TODO fix this, use AO names to channel number to autopopulate

    fig, axes = plt.subplots(nrows=1, ncols=1, figsize=(10, 9))
    axes.set_title("One Frame.")
    axes.plot(t, etl_t, label="etl")
    axes.plot(t, laser_488_enable_t, label="488 laser enable")
    axes.plot(t, laser_561_enable_t, label="561 laser enable")
    axes.plot(t, laser_638_enable_t, label="638 laser enable")
    axes.plot(t, laser_405_enable_t, label="405 laser enable")
    axes.plot(t, camera_enable_t, label="camera enable")
    axes.plot(t, stage_enable_t, label="stage_enable")
    axes.plot(t, galvo_a_t, label="galvo_a")
    axes.plot(t, galvo_b_t, label="galvo_b")
    axes.set_xlabel("time [s]")
    axes.set_ylabel("amplitude [V]")
    axes.set_ylim(0, 5)
    axes.legend(loc="upper right")
    fig.savefig("plot.pdf")


def generate_waveforms(cfg, plot: bool = False, channels: list[int] = None, live = False):
    voltages_t = {}
    total_samples = 0

    # Create lookup table to go from ao channel name to voltages_t index.
    #   This must match the order the NI card will create them.
    # name to channel index (i.e: hardware pin number) lookup table:
    n2c_index = {name: index for index, (name, _) in enumerate(cfg.n2c.items())}

    # Create samples arrays for various relevant timings
    camera_exposure_samples = int(cfg.daq_sample_rate * cfg.camera_exposure_time)
    rest_samples = int(cfg.daq_sample_rate * cfg.frame_rest_time)
    dwell_time_samples = int(cfg.daq_sample_rate * cfg.camera_dwell_time)
    pulse_samples = int(cfg.daq_sample_rate * cfg.ttl_pulse_time)
    channels_list = cfg.channels if channels is None else channels
    for ch in channels_list:
        # Create channel-specific samples arrays for various relevant timings
        camera_delay_samples = int(cfg.daq_sample_rate * cfg.get_camera_delay_time(ch))
        etl_buffer_samples = int(cfg.daq_sample_rate * cfg.get_etl_buffer_time(ch))
        channel_samples = camera_exposure_samples + etl_buffer_samples + rest_samples + dwell_time_samples

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

        voltages_t[ch][n2c_index['etl'], 0:camera_exposure_samples + etl_buffer_samples] = voltages_etl  # write in ETL sawtooth
        voltages_t[ch][n2c_index['etl'], camera_exposure_samples + etl_buffer_samples::] = cfg.get_etl_offset(ch) + cfg.get_etl_amplitude(ch)  # snap back ETL after sawtooth
        voltages_t[ch][n2c_index['etl'],
        camera_exposure_samples + etl_buffer_samples:camera_exposure_samples + etl_buffer_samples + dwell_time_samples] = \
            cfg.get_etl_offset(ch) - cfg.get_etl_amplitude(ch)  # delay snapback until last row is done exposing

        # Generate camera TTL signal
        voltages_t[ch][n2c_index['camera'], int(etl_buffer_samples / 2.0) + camera_delay_samples:int(
            etl_buffer_samples / 2.0) + camera_delay_samples + pulse_samples] = 5.0

        # Generate laser TTL signal
        voltages_t[ch][n2c_index[str(ch)],  # FIXME: remove n2c or move it into the config.
        int(etl_buffer_samples / 2.0) + camera_delay_samples:int(
            etl_buffer_samples / 2.0) + camera_exposure_samples + dwell_time_samples + camera_delay_samples] = 4.0

        # Generate stage TTL signal
        if ch == channels_list[-1]:
            volts = 5.0 if not live else 0.0
            voltages_t[ch][n2c_index['stage'],
                           camera_exposure_samples + etl_buffer_samples + dwell_time_samples:
                           camera_exposure_samples + etl_buffer_samples + dwell_time_samples + pulse_samples] = volts

        # Generate galvo signals
        voltages_t[ch][n2c_index['galvo_a']] = cfg.get_galvo_a_setpoint(ch)
        voltages_t[ch][n2c_index['galvo_b']] = cfg.get_galvo_b_setpoint(ch)

    # Merge voltage arrays
    voltages_out = np.array([]).reshape((len(cfg.n2c), 0))
    for ch in channels_list:
        voltages_out = np.hstack((voltages_out, voltages_t[ch]))

    if plot:
        # Total waveform time in sec.
        t = np.linspace(0, cfg.daq_period_time, total_samples, endpoint=False)
        plot_waveforms_to_pdf(t, voltages_out)

    return voltages_out

