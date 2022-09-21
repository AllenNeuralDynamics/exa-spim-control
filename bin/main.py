#!/usr/bin/env python3
"""main script to launch the exaspim with a config.toml file."""

from exaspim.exaspim import Exaspim
import ctypes
import argparse
import os

# We need a separate main function to install from the package as a script.
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--log_level", type=str, default="INFO",
                        choices=["INFO", "DEBUG"])
    parser.add_argument("--simulated", default=False, action="store_true",
                        help="Simulate hardware device connections.")
    # Note: colored console output is buggy on Windows.
    parser.add_argument("--color_console_output", action="store_true",
                        default=False if os.name == 'nt' else True)

    args = parser.parse_args()
    # Check if we didn't supply a config file and populate a safe guess
    # depending on whether or not we're simulating.
    if not args.config:
        if args.simulated:
            args.config = "./sim_config.toml"
        else:
            args.config = "./config.toml"

    # Windows-based console needs to accept colored logs if running with color.
    if os.name == 'nt' and args.color_console_output:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    instrument = Exaspim(config_filepath=args.config,
                        console_output_level=args.log_level,
                        color_console_output=args.color_console_output,
                        simulated=args.simulated)
    try:
        #from inpromptu import Inpromptu
        #Inpromptu(instrument).cmdloop()
        instrument.run(overwrite=args.simulated)
    except KeyboardInterrupt:
        pass
    finally:
        instrument.close()


if __name__ == '__main__':
    main()
