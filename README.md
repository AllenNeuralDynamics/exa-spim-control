# exa-spim-control
Acquisition control for the exaSPIM microscope system

## Prerequisites
This program has substantial platform memory requirements (~103 GB for 4 channel imaging).
These ram requirements are largely due to the chunk size of the online compressor (ImarisWriter) which performs best with larger chunks.
Recommended requirements are:
* CPU with 8 cores
* 128 GB of ram, ideally on a single memory card

## Installation
From this folder install this python package with:
````
pip install -e .
````
There are a few additional software components to install.
Read on for installation instructions.

### Manual Components
#### eGrabber
You will need [egrabber for coaxlink and gigelink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f) installed for your particular system.
Note that, to download the egrabber sdk, you will first need to make an account with them.
After downloading and installing eGrabber, you will need to install the eGrabber python package (stored as a wheel file).
For more info installing the python whl file, see the [notes from Euresys](https://documentation.euresys.com/Products/COAXLINK/COAXLINK/en-us/Content/04_eGrabber/programmers-guide/Python.htm).

Generally, the process should be as simple as finding the whl package in the eGrabber subfolder and invoking:
````
pip install egrabber-22.05.3.77-py2.py3-none-any.whl
````
Note that the above version above be slightly different.

#### eGrabber
On Linux you will also need to compile and install [ImarisWriter](https://github.com/imaris/ImarisWriter).
Note that, additionally, the PyImarisWriter.py file installed with pip may 
be out of date and need to be replaced with the [latest version on Github](https://github.com/imaris/ImarisWriter/blob/master/python/PyImarisWriter/PyImarisWriter.py).
Otherwise, you may get a [segfault](https://github.com/imaris/ImarisWriter/pull/6).

**TODO: is this the right way to do this?**

After compiling ImarisWriter on Linux, it needs to be recognized system-wide with:
````bash
sudo make install
ldconfig -n /abs/path/to/ImarisWriter/release/lib
````

## Run

### as an executable
This method is convenient for launching the code on a PC plumbed with all the necessary hardware (Camera, galvos, etc.).
A thin prompt-based UI is exposed for interacting with the machine.

With the package installed, you can launch the code from a command prompt by invoking `exaspim`.
This will run the exaspim with a config.toml file in the current directory.
To specify a config.toml file located elsewhere, use:

````python
exaspim --config /path/to/config.toml
````

It may be useful to run the package in "simulated" mode, which will dry-run the data acquisition loop on fake images with parameters from a config file.
All hardware connections are spoofed.
This mode is useful for tweaking config values like the ImarisWriter "chunk size" and ensuring that your pc has enough ram and disk space to run an acquisition.
````python
exaspim --simulated
````

It is also possible to change the output log level:
````python
exaspim --log_level DEBUG
````

### As a Package
This method is convenient for developing GUIs on top of the Exaspim class for interacting with the machine as a production instrument.
````python
from exaspim.exaspim import Exaspim
from exaspim.exaspim_config import ExaspimConfig

cfg = ExaspimConfig("config.toml")
instrument = Exaspim(cfg)
instrument.run()
````
