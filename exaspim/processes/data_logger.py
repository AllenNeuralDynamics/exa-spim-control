import glob
import logging
import os
import subprocess
import time
from pathlib import Path


class DataLogger:

    def __init__(self, source_path: Path, memento_exe_path: Path, tile_name):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.source_path = source_path
        self.memento_path = memento_exe_path
        self.tile_name = tile_name
        self.cmd = None
        if not self.memento_path.exists():
            self.log.error("Memento executable path does not exist.")
        if not self.source_path.exists():
            error = "Memento output destination path " \
                    f"{str(self.source_path)} cannot be found."
            self.log.error(error)
            raise FileNotFoundError(error)

    def start(self):
        if not self.memento_path.exists():
            self.log.error("Aborting start. Cannot find memento executable.")
            return
        cmd_text = f"{str(self.memento_path)} dump " \
                   f"--output={str(self.source_path)}\\dump.memento --follow"
        self.cmd = subprocess.Popen(cmd_text)
        time.sleep(1)  # takes time for memento to boot sometimes

    def stop(self):
        if not self.memento_path.exists():
            self.log.error("Aborting stop. Cannot find memento executable.")
            return
        # Terminate the memento subprocess.
        subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.cmd.pid)])
        self.cmd.wait()

    def close(self):
        if not self.memento_path.exists():
            self.log.error("Aborting close. No memento log was created.")
            return
        # TODO: figure out why we need to rename at the end.
        fname = glob.glob(str(self.source_path) + 'dum*.memento')
        os.rename(fname[0], str(self.source_path) + self.tile_name + '.memento')
