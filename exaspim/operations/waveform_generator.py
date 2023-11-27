import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy import interpolate


def plot_waveforms_to_pdf(t, voltages_t):

    etl_t, camera_enable_t, stage_enable_t, laser_488_enable_t, laser_638_enable_t, laser_561_enable_t, laser_405_enable_t = voltages_t  # TODO fix this, use AO names to channel number to autopopulate

    fig, axes = plt.subplots(nrows=1, ncols=1, figsize=(10, 9))
    axes.set_title("One Frame.")
    axes.plot(t, etl_t, label="etl")
    axes.plot(t, laser_488_enable_t, label="488 laser enable")
    axes.plot(t, laser_561_enable_t, label="561 laser enable")
    axes.plot(t, laser_638_enable_t, label="638 laser enable")
    axes.plot(t, laser_405_enable_t, label="405 laser enable")
    axes.plot(t, camera_enable_t, label="camera enable")
    axes.plot(t, stage_enable_t, label="stage_enable")
    axes.set_xlabel("time [s]")
    axes.set_ylabel("amplitude [V]")
    axes.set_ylim(0, 5)
    axes.legend(loc="upper right")
    fig.savefig("plot.pdf")

def generate_waveforms(cfg, channel: int, plot: bool = False, live = False):

    # Create lookup table to go from ao channel name to voltages_t index.
    #   This must match the order the NI card will create them.
    # name to channel index (i.e: hardware pin number) lookup table:
    n2c_index = {name: index for index, (name, _) in enumerate(cfg.n2c.items())}

    # Create samples arrays for various relevant timings
    camera_exposure_samples = int(cfg.daq_sample_rate * cfg.camera_exposure_time)
    dwell_time_samples = int(cfg.daq_sample_rate * cfg.camera_dwell_time)

    # Create channel-specific samples arrays for various relevant timings
    rest_samples = int(cfg.daq_sample_rate * cfg.get_frame_rest_time(channel))
    pulse_samples = int(cfg.daq_sample_rate * cfg.get_ttl_pulse_time(channel))
    etl_buffer_samples = int(cfg.daq_sample_rate * cfg.get_etl_buffer_time(channel))
    total_samples = camera_exposure_samples + etl_buffer_samples + rest_samples + dwell_time_samples

    voltages_out = np.zeros((len(cfg.n2c), total_samples))

    # Generate ETL signal
    t_etl = np.linspace(0, cfg.camera_exposure_time + cfg.get_etl_buffer_time(channel),
                        camera_exposure_samples + etl_buffer_samples, endpoint=False)
    voltages_etl = -cfg.get_etl_amplitude(channel) * signal.sawtooth(
        2 * np.pi / (cfg.camera_exposure_time + cfg.get_etl_buffer_time(channel)) * t_etl, width=1.0) + cfg.get_etl_offset(channel)
    t0 = t_etl[0]
    t1 = t_etl[int((camera_exposure_samples + etl_buffer_samples) * cfg.get_etl_interp_time(channel))]
    tf = t_etl[-1]
    v0 = voltages_etl[0]
    v1 = voltages_etl[int((camera_exposure_samples + etl_buffer_samples) * cfg.get_etl_interp_time(channel))] + cfg.get_etl_nonlinear(channel)
    vf = voltages_etl[-1]
    f = interpolate.interp1d([t0, t1, tf], [v0, v1, vf], kind='quadratic')
    voltages_etl = f(t_etl)

    voltages_out[n2c_index['etl'], 0:camera_exposure_samples + etl_buffer_samples] = voltages_etl  # write in ETL sawtooth
    voltages_out[n2c_index['etl'], camera_exposure_samples + etl_buffer_samples::] = cfg.get_etl_offset(channel) + cfg.get_etl_amplitude(channel)  # snap back ETL after sawtooth
    voltages_out[n2c_index['etl'],
    camera_exposure_samples + etl_buffer_samples:camera_exposure_samples + etl_buffer_samples + dwell_time_samples] = \
    cfg.get_etl_offset(channel) - cfg.get_etl_amplitude(channel)  # delay snapback until last row is done exposing

    # Generate camera TTL signal
    voltages_out[n2c_index['camera'], int(etl_buffer_samples / 2.0):int(
        etl_buffer_samples / 2.0) + pulse_samples] = 5.0

    # Generate laser TTL signal
    voltages_out[n2c_index[f'laser_{channel}'],  # FIXME: remove n2c or move it into the config.
    int(etl_buffer_samples / 2.0):int(
        etl_buffer_samples / 2.0) + camera_exposure_samples + dwell_time_samples] = cfg.get_channel_ao_voltage(str(channel))

    # Generate stage TTL signal
    volts = 5.0 if not live else 0.0
    voltages_out[n2c_index['stage'],
                   camera_exposure_samples + etl_buffer_samples + dwell_time_samples:
                   camera_exposure_samples + etl_buffer_samples + dwell_time_samples + pulse_samples] = volts

    if plot:
        # Total waveform time in sec.
        t = np.linspace(0, cfg.get_channel_cycle_time(channel), total_samples, endpoint=False)
        plot_waveforms_to_pdf(t, voltages_out)

    return voltages_out