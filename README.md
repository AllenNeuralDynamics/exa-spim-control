# exa-spim-control
Acquisition control for the exaSPIM microscope system

## Installation

### Prerequisites
You will need [egrabber for coaxlink and gigelink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f) installed for your particular system.
Note that, to download the egrabber sdk, you will first need to make an account with them.

On Linux you will need [ImarisWriter](https://github.com/imaris/ImarisWriter) compiled and installed.
*Note that PyImarisWriter may need to be tweaked to load a linux \*.so file instead of a windows \*.dll file before the ctype bindings work.*

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
Note that a fairly recent version of pip (>=21.3) is required.

## Run
With the package installed, you can launch the code from a command prompt by invoking `exaspim`.
