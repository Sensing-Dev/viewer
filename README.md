
# Viewer

This repository contains a GUI implementation for real-time video display and saving. It currently supports cameras using the **USB3 protocol**.

## Requirement 
1. `aravis-python==0.8.31`
2. `ion-contrib-python==3.2.5`

To install the necessary packages, run:
```bash
python3 -m pip install -r requirements.txt
```

## Test Environment
- Ubuntu22.04 + v1.2 camera
- TBD Windows

## Usage

To run the application, use the following command format:
### Running Option
```
python3 gui.py [options]
```

Command-Line Arguments

- `-d`, `--directory` (default: `./output`)
  - **Description**: Directory where saved files will be saved.
  - **Type**: `str`
  
- `-g`, `--gain-key-name` (default: `Gain`)
  - **Description**: Name of the Gain key defined for the GenICam feature.
  - **Type**: `str`
  
- `-e`, `--exposuretime-key-name` (default: `ExposureTime`)
  - **Description**: Name of the ExposureTime key defined for the GenICam feature.
  - **Type**: `str`
  
- `-nd`, `--number-of-device` (default: `2`)
  - **Description**: The number of cameras to be used.
  - **Type**: `int`
  
- `-rt`, `--realtime-display-mode` (default: `True`)
  - **Description**: Set camera display to real-time display.
  - **Type**: `bool` (Optional argument; default is enabled)
  
- `-sync`, `--frame-sync-mode` (default: `False`)
  - **Description**: If the number of devices is greater than 1, synchronize the frame counts of 2 cameras.
  - **Type**: `bool` (Optional argument; default is disabled)
  
- `--sim-mode` (default: `False`)
  - **Description**: Enable simulation mode.
  - **Type**: `bool`
  
- `--pixel-format` (default: `Mono8`)
  - **Description**: Pixel format to use (valid only if sim mode is active).
  - **Type**: `str`

### Running in Simulation Mode

To start the application in simulation mode, use the command below, ensuring that the arv-fake-camera.xml file path is correct:
```
export GENICAM_FILENAME=<where your arv-fake-camera.xml located>
python3 gui.py --sim-mode --pixel-format=BayerBG8
```

### Running in Non-Simulation Mode
For standard operation, run:
```
python3 gui.py
```

## Completed Features

1. Display support for 1 or 2 cameras.
2. Toggle between Gendc Mode: ON and Gendc Mode: OFF.
3. Adjust parameters using the slider and spin box.
4. Save images, videos, or binary data using the Start and Stop buttons.
5. Save binary image data for a specified number of seconds.

#### Gendc Mode Details

- when Gendc mode:ON, bin file saved in GenDC format and is started with GENC signature
- when Gendc mode:OFF, bin file only includes image binary


## Notes

- when the image is gray-scale, it is useless to slide the r, g, b gain, please slide the gain and exposure time
- jpeg/jpg/bmp support 8 bits, and png/raw/mp4 support 8/16 bits 
