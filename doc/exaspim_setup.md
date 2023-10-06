# exaSPIM Setup Guide
1. Download all necessary driver/software. Some of the UI’s are convenient for trouble shooting hardware  
   -   [Pycharm](https://www.jetbrains.com/pycharm/download/download-thanks.html?platform=windows&code=PCC) or whatever python interpreter to write code. I like pycharm
   -   Tiger ASI driver for the [USB serial adapter](https://www.asiimaging.com/support/downloads/usb-support-on-ms-2000-wk-controllers/) 
   -   [Tiger Control Panel ](http://asiimaging.com/docs/tiger_control_panel) 
    
     - [Gitbash](https://gitforwindows.org/)- IMPORTANT when prompted let git be added to PATH. Makes things easier downstream. Computer will need to be restarted 

     - [Anaconda](https://www.anaconda.com/) or another python console interpreter. I like anaconda to make environments and stuff in prompt. IMPORTANT add anaconda to PATH when prompted it will save headache in the future.  

     - [Ni-DAQ Driver](https://www.ni.com/en/support/downloads/drivers/download/packaged.ni-daq-mx.484356.html)  

     - Camera driver e.g. [egrabber for coaxlink and gigelink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f).After downloading and installing eGrabber, you will need to install the eGrabber python package (stored as a wheel file). To install, open conda, navigatre to egrabber subfolder and write:
       -       C:\Program Files\eGrabber\> pip install egrabber-22.05.3.77-py2.py3-none-any.whl
   
2. Create [ssh keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent) in git and add them to your account 
3. Sign into your github account on [gitbash](https://stackoverflow.com/questions/8840551/configuring-user-and-password-with-git-bash)
4. Clone all necessary repos with ssh keys
   -    [Spim-core](https://github.com/AllenNeuralDynamics/spim-core) 

   -   [TigerASI](https://github.com/AllenNeuralDynamics/TigerASI)

   -   [Aind-data-schema](https://github.com/AllenNeuralDynamics/aind-data-schema) 

   -   [SPIM-UI-Launch](https://github.com/AllenNeuralDynamics/SPIM-UI-Launch) 

   -   [exaSpim-UI](https://github.com/AllenNeuralDynamics/exaSpim-UI)

   -   [exa-spim-control](https://github.com/AllenNeuralDynamics/exa-spim-control/tree/dev/gui_tweaks)  

   -   Laser repos ([oxxius_laser](https://github.com/AllenNeuralDynamics/oxxius_laser), [vortran_laser](https://github.com/AllenNeuralDynamics/vortran_laser), [obis-laser](https://github.com/AllenNeuralDynamics/obis-laser))
5. Create a new environment in Anaconda prompt OR create an environment from the yml file in the exaspim-UI repo. There is also a requirements.txt file in dispim-UI repo that will auto pip install required modules when you pip install dispim-UI repo. 

   -        conda create -n myenv python=3.9 

    OR 

   -        conda env create -f environment.yml
6. Activate environment, navigate to repo,  and pip install all pip installable repos 
    ```
    (base) C:\Users\hcr-fish>conda activate exaspim 
    (dispim1) C:\Users\hcr-fish\Projects\spim-core>pip install -e .
   ```
7. Once everything is installed correctly (you may have to trouble shoot if certain packages aren’t installed) then go to the device manager and update the com ports in the config.toml file for the correct devices.  
8. Run exaspim_main.py in exaspim_UI repo and hopefully napari will pop up no problem 

   -   If you have trouble connecting to lasers, switch lasers on and off and turn interlock on and back off 

   -   If napari won’t pop up, check the console and see if you’re missing a pip installable package
9. Install [fio](https://github.com/axboe/fio#id5)

  -   If using spim-core,  need to install fios. I found it hard, but I’m sure it’ll be a piece of cake for you!
  - Clone the repo into projects folder 
  - The fio repo has a pretty detailed install but just incase I’ll reiterate what worked for me
  - Download the latest [fio msi windows installer](https://github.com/axboe/fio/releases) 
  - Download cygwin. IMPORTANT: when installing Cygwin, it will ask you what packages you want installed. Specify make and then any packages starting with mingw64-x86_64 
  - Open cyqwin terminal and navigate to the drive your working from. For example, mine was the c drive so type:
    -       cd /cygdrive/c 
  - Navigate to the projects folder where you cloned the fio repo 
    -     cd   /cygdrive/c/users/micah.woodard/projects/fio 
    -   Then run
          ```
          ./configure 
        
          make 
        
          make install 

        ```
-   IMPORTANT: I had to delete the block comments found in the configure file before this would run and it still complained a little about $’\r’ not being found but it did work.  

-   Make sure to close any pycharm or command prompt instances before trying to use command fio 

 

TROUBLESHOOTING HARDWARE : 

Stage: 
1.  Problem- Responses from stage have strange characters intermixed within reply. 

2.  Cause- The Tiger Controller cards are physically addressed and hardcoded in the field to a certain card number. This is listed on the top of the front panel of the card. The physical order (left to right) in the controller does not matter, but there cannot be duplicates of the same card number at the same time. In the in the event that there are duplicates, there can be strange behavior. For example, both duplicated cards may not appear properly to the controller, other cards could be impacted, and the overall communication in/out of the controller may be corrupted. 

3.  Solution- Remove one of the duplicated cards. If both need to be connected at the same time, the card must be physically shipped back to ASI for a reflash of new firmware. WARNING: never remove a card from the controller when it is powered ON. This can 'brick' and destroy the entire controller and/or card(s). 

 

1.  Problem- The two twin vertical stages (usually Z/F axes) are corrupt and blink red repeatedly after being moved. 

2.  Cause- The two vertical stages are usually coupled together, where the F is 'slave' to the Z axis. If the two axes get off from one another too much in their position, the controller will lock them out and flash red indicating an error. You can visually inspect the two risers to roughly check if they are at the same position or not or check the Tiger UI positions tab. 

3.  Solution- If one axis is  very far off from the other, you can explicitly tell the F axis to move to a certain position using the MOVEREL or MOVE commands. Be very careful here, and ideally detached anything like a XY stage that is attached to both vertical stages. Because if things go awry, this could mechanically damage and torque the XY stage. Alternatively, you could connect the cables from the ZF stages to a different card, like the XY card. In this case you could use the joystick to independently move both risers to the same location. Same caution here, detach anything attached to both vertical stages. 

 