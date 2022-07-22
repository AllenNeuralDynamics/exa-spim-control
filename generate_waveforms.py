#!/usr/bin/env python3
"""Generate waveforms from params below. If standalone, save a graph only."""
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal


def generate_waveforms():
    """return a numpy nd array with the correct waveforms."""

    # inputs: TODO fold this into config throughout.
    rate = 1e4
    etl_amplitude = 0.35/2.0 # volts
    etl_offset = 2.155 + etl_amplitude # volts
    camera_exposure_time = 15/1000*10640/1000 # sec
    camera_delay_time = 6.5/1000 # sec
    etl_buffer_time = 25.0/1000 # sec
    laser_buffer_time = 5.0/1000 # sec
    rest_time = 25.4/1000 # sec
    line_time = 5.0/1000 # sec
    pulse_time = 10.0/1000 # sec
    total_time = camera_exposure_time + etl_buffer_time + rest_time

    # Create samples arrays for various relevant timings
    camera_exposure_samples = int(rate*camera_exposure_time)
    camera_delay_samples = int(rate*camera_delay_time)
    etl_buffer_samples = int(rate*etl_buffer_time)
    laser_buffer_samples = int(rate*laser_buffer_time)
    rest_samples = int(rate*rest_time)
    line_time_samples = int(rate*line_time)
    pulse_samples = int(rate*pulse_time)
    total_samples = camera_exposure_samples + etl_buffer_samples + rest_samples

    # Initialize 2D voltages array
    voltages_t = np.zeros((4, total_samples)) # TODO fix this from being hardcoded to 4

    # Generate ETL signal
    t_etl = np.linspace(0, camera_exposure_time + etl_buffer_time, camera_exposure_samples + etl_buffer_samples, endpoint = False)
    voltages_etl = -etl_amplitude*signal.sawtooth(2*np.pi/(camera_exposure_time + etl_buffer_time)*t_etl, width = 1.0) + etl_offset
    voltages_t[0, 0:camera_exposure_samples + etl_buffer_samples] = voltages_etl # write in ETL sawtooth
    voltages_t[0, camera_exposure_samples + etl_buffer_samples::] = etl_offset + etl_amplitude # snap back ETL after sawtooth
    voltages_t[0, camera_exposure_samples + etl_buffer_samples:camera_exposure_samples + etl_buffer_samples + line_time_samples] = etl_offset - etl_amplitude # delay snapback until last row is done exposing

    # Generate camera TTL signal
    voltages_t[1, int(etl_buffer_samples/2.0)+camera_delay_samples:int(etl_buffer_samples/2.0) + camera_delay_samples + pulse_samples] = 5.0

    # Generate stage TTL signal
    voltages_t[2, camera_exposure_samples + etl_buffer_samples + line_time_samples:camera_exposure_samples + etl_buffer_samples + line_time_samples + pulse_samples] = 5.0

    # Generate laser TTL signal
    voltages_t[3, int(etl_buffer_samples/2.0)-laser_buffer_samples:int(etl_buffer_samples/2.0) + camera_exposure_samples + line_time_samples] = 5.0

    # Total waveform time in sec
    t = np.linspace(0, total_time, total_samples, endpoint = False)

    return t, voltages_t


def plot_waveforms_to_pdf(t, voltages_t):
    """Write a pdf plot output of the waveforms."""

    # Make references
    etl_t, camera_enable_t, stage_enable_t, laser_enable_t = voltages_t # TODO fix this, use AO names to channel number to autopopulate

    # Plot the data for sanity checking.
    fig, axes = plt.subplots(nrows=1, ncols=1, figsize=(10, 7))

    # first plot: the whole thing.
    axes.set_title("One Frame.")
    axes.plot(t, etl_t, label="etl")
    axes.plot(t, laser_enable_t, label="laser enable")
    axes.plot(t, camera_enable_t, label="camera enable")
    axes.plot(t, stage_enable_t, label="stage_enable")
    axes.set_xlabel("time [s]")
    axes.set_ylabel("amplitude [V]")
    axes.legend(loc="center")#loc="center left")

    try:
        fig.savefig("plot.pdf")
    except OSError as e:
        print("Error: cannot save figure. Another program may be using it.")
        raise e

if __name__ == "__main__":
    t, voltages_t = generate_waveforms()
    plot_waveforms_to_pdf(t, voltages_t)
