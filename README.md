# exa-spim-control
Acquisition control for the exaSPIM microscope system

## Installation

### Prerequisites
You will need [egrabber for coaxlink and gigelink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f) installed for your particular system.
Note that, to download the egrabber sdk, you will first need to make an account with them.

On Linux you will need [ImarisWriter](https://github.com/imaris/ImarisWriter) compiled and installed.
*Note that PyImarisWriter may need to be tweaked to load a linux \*.so file instead of a windows \*.dll file before the ctype bindings work.*

## TODO: is this the right way to do this?
After compiling ImarisWriter on Linux, it needs to be installed with:
````bash
sudo make install
ldconfig -n /home/poofjunior/projects/ImarisWriter/release/lib
````

### Installing

With egrabber installed via script, enter the downloaded folder's *python* folder and invoke:
````
pip install egrabber-22.05.3.77-py2.py3-none-any.whl
````
Note that the above version might be slightly different.

Next, from this folder install this python package with:
````
pip install -e .
````

## Run

### As Executable
This method is convenient for launching the code on a PC plumbed with all the necessary hardware (Camera, galvos, etc.).
A thin prompt-based UI is exposed for interacting with the machine.

With the package installed, you can launch the code from a command prompt by invoking `exaspim`.

TODO: command line arguments.

### As a Package
This method is convenient for developing GUIs on top of the Exaspim class for interacting with the machine as a production instrument.
````python
from exaspim.exaspim import Exaspim

instrument = Exaspim(args)
instrument.run()
````
