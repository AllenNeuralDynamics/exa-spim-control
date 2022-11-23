"""Test Script for running n processes standalone with the specs below."""

import numpy as np
from exaspim.data_structures.shared_double_buffer import SharedDoubleBuffer
from exaspim.processes.stack_writer import StackWriter
from multiprocessing import Process, Array, Event
from multiprocessing.shared_memory import SharedMemory
from ctypes import c_wchar
from PyImarisWriter import PyImarisWriter as pw
from pathlib import Path
from datetime import datetime
from matplotlib.colors import hex2color
from time import sleep, perf_counter
from math import floor, ceil

from pathlib import Path
import copy
import os
import psutil

def get_mem_usage():
    current_process = psutil.Process(os.getpid())
    mem = current_process.memory_percent()
    for child in current_process.children(recursive=True):
        mem += child.memory_percent()
    return mem

rows = 10640
cols = 14192
num_frames = 100#500
chunk_size = 32#64
num_processes = 4

kwargs = {
    "image_rows": rows,
    "image_columns": cols,
    "image_count": num_frames,  # TODO: figure out why non-chunk-size multiples are hanging.
    "first_img_centroid_x": 0,
    "first_img_centroid_y": 0,
    "pixel_x_size_um": 7958.72,
    "pixel_y_size_um": 10615.616,
    "pixel_z_size_um": 1,
    "chunk_size": chunk_size,
    "thread_count": 32,  # This is buggy at very low numbers?
    "compression_style": 'lz4',
    "datatype": "uint16",
    "dest_path": Path("."),
    "stack_name": "test",
    "channel_name": "0",
    "viz_color_hex": "#00ff92"
}

if __name__ == "__main__":
    start_time = perf_counter()
    print(f"Starting mem usage: {get_mem_usage()}")
    ps_buffers = [SharedDoubleBuffer((cols, rows, chunk_size), "uint16")
                  for i in range(num_processes)]
    print(f"Mem usage after SharedDoubleBuffer allocation: {get_mem_usage()}")
    ps_workers = []
    try:
        print(f"Creating and starting {num_processes} processes.")
        for i in range(num_processes):
            kwds = copy.deepcopy(kwargs)
            kwds["stack_name"] = f"test_process_{i}"
            kwds["channel_name"] = f"{i}"
            ps_workers.append(StackWriter(**kwds))
            ps_workers[-1].start()
        print(f"Producing data.")
        last_frame_index = num_frames - 1
        for frame_index in range(num_frames):
            chunk_num = floor(frame_index / chunk_size)
            chunk_index = frame_index % chunk_size
            #print(f"frame: {frame_index} | chunk_num: {chunk_num} | chunk_index: {chunk_index}")
            # Write some data into each buffer
            for ps_buffer in ps_buffers:
                # Create fake data. Replace with cam.grab_frame() or similar.
                ps_buffer.write_buf[chunk_index][:, :] = chunk_index
            # Dispatch chunk if it is full
            if chunk_index == chunk_size-1 or frame_index == last_frame_index:
                for ps_buffer, ps_worker in zip(ps_buffers, ps_workers):
                    ps_buffer.toggle_buffers()
                    # Send over the read buffer shm name.
                    ps_worker.shm_name = ps_buffer.read_buf_mem_name
                    ps_worker.done_reading.clear()
            # Wait for all processes to finish before sending more data.
            # TODO: we can probably handle this more elegantly.
            print("Waiting for processes to handle new data.")
            print(f"Mem usage during operation: {get_mem_usage()}")
            while not all([ps.done_reading.is_set() for ps in ps_workers]):
                sleep(0.001)
            #for ps_worker in ps_workers:
            #    ps_worker.done_reading.wait()
    finally:
        # kill the process? TODO
        #data_writer_worker.terminate()
        print("Joining processes")
        for ps_worker in ps_workers:
            ps_worker.join()
        total_frames = num_frames*num_processes
        elapsed_time = perf_counter() - start_time
        print(f"{total_frames} images compressed in "
              f"{elapsed_time:.3f} seconds. "
              f"Current performance metrics can handle an input image "
              f"stream up to {total_frames/elapsed_time:.3f} [fps].")
        # Release shared memory.
        print("Unlinking shared memory.")
        for ps_buffer in ps_buffers:
            ps_buffer.close_and_unlink()