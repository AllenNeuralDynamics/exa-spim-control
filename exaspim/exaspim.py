"""Abstraction of the ExaSPIM Instrument."""

from mesospim.spim_base import Spim
from config import ExaspimConfig


class Exaspim(Spim):

    def __init__(self, config_filepath: str, log_filename: str = 'debug.log',
                 console_output: bool = True,
                 color_console_output: bool = False,
                 console_output_level: str = 'info', simulated: bool = False)

        super().__init__(config_filepath, log_filename, console_output,
                         color_console_output, console_output_level, simulated)
        self.cfg = ExaspimConfig(config_filepath)

    def run_from_config(self):
        pass

    def close(self):
        """Safely close all open hardware connections."""
        # stuff here.
        super().close()
