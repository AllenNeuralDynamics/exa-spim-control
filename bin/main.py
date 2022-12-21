#!/usr/bin/env python3
"""main script to launch the exaspim with a config.toml file."""

from exaspim.exaspim import Exaspim
from coloredlogs import ColoredFormatter
import ctypes
import logging
import argparse
import os
import sys
import traceback

# Remove any handlers already attached to the root logger.
logging.getLogger().handlers.clear()


class SpimLogFilter(logging.Filter):
    # Note: add additional modules that we want to catch here.
    VALID_LOGGER_BASES = {'mesospim', 'exaspim', 'tigerasi'}

    def filter(self, record):
        """Returns true for a record that matches a log we want to keep."""
        return record.name.split('.')[0].lower() in \
            self.__class__.VALID_LOGGER_BASES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--log_level", type=str, default="INFO",
                        choices=["INFO", "DEBUG"])
    parser.add_argument("--simulated", default=False, action="store_true",
                        help="Simulate hardware device connections.")
    parser.add_argument("--overwrite", default=False, action="store_true",
                        help="allow overwriting data in preexisting folders.")
    parser.add_argument("--console_output", default=True,
                        help="whether or not to print to the console.")
    # Note: colored console output is buggy on Windows.
    parser.add_argument("--color_console_output", action="store_true",
                        default=True)
                        #default=False if os.name == 'nt' else True)

    args = parser.parse_args()
    # Check if we didn't supply a config file and populate a safe guess.
    if not args.config:
        if args.simulated:
            args.config = "./sim_config.toml"
        else:
            args.config = "./config.toml"

    # Setup logging.
    # Create log handlers to dispatch:
    # - User-specified level and above to print to console if specified.
    logger = logging.getLogger()  # get the root logger.
    # logger level must be set to the lowest level of any handler.
    logger.setLevel(logging.DEBUG)
    fmt = '%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s'
    fmt = "[SIM] " + fmt if args.simulated else fmt
    datefmt = '%Y-%m-%d,%H:%M:%S'
    log_formatter = ColoredFormatter(fmt=fmt, datefmt=datefmt) \
        if args.color_console_output \
        else logging.Formatter(fmt=fmt, datefmt=datefmt)
    if args.console_output:
        log_handler = logging.StreamHandler(sys.stdout)
        log_handler.addFilter(SpimLogFilter())
        log_handler.setLevel(args.log_level)
        log_handler.setFormatter(log_formatter)
        logger.addHandler(log_handler)

    # Windows-based console needs to accept colored logs if running with color.
    if os.name == 'nt' and args.color_console_output:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    instrument = Exaspim(args.config, args.simulated)
    try:
        instrument.run(overwrite=args.simulated or args.overwrite)
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
    finally:
        instrument.close()

if __name__ == '__main__':
    main()
