# RTX-Remix-Downloader

A simple downloader for the latest RTX-Remix releases.
This script requests the latest artifact builds from the official Github repositories.

It will pull the latest files from the following NVIDIAGameWorks repos 
* [rtx-remix](https://github.com/NVIDIAGameWorks/rtx-remix)
* [dxvk-remix](https://github.com/NVIDIAGameWorks/dxvk-remix/)
* [bridge-remix](https://github.com/NVIDIAGameWorks/bridge-remix/)

## Installation
Simply move the .exe file to a folder or desktop and run it. It will create a subdirectory called "Remix" that contains all the files it downloaded.

## Usage
Execute the script and follow the instructions shown in the window.
Once the script finishes you'll find a fully patched RTX Remix install in the Remix folder next to the .exe file, you can then follow the normal [installation guide for RTX Remix](https://github.com/NVIDIAGameWorks/rtx-remix/wiki/runtime-user-guide).

## Known Issues
Currently only works on the same drive that the temp folder is on due to PathLib not supporting moving of files across drives. A fix is being worked on.

## Support
Find us on Discord: [RTX Remix Showcase](https://discord.gg/rtxremix)

Script created by @Kowlin with some nagging by @RuneStorm
Original PowerShell script version by @Kowlin & @RuneStorm

This Project is in no way directly affiliated with NVIDIA or the RTX Remix project.
