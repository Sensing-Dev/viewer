## Changelog

### Update 2024-09-13
1. fix and enabled delete checkbox
2. add delete option to json file
3. fix the error in non-gendc mode with gendc device

### Update 2024-09-06:
1. add delete checkbox
2. updated to **ion-Kit 3.2.0**.

### Update 2024-09-01:
1. set the range of RGB control bars from 0.0 to 3.0.
2. fix the bug on text box
3. add the feature to save the setting
4. still save other formats on GenDC mode

### Update 2024-08-26:
1. Created two independent threads for image previewing (RGB processing) and shooting.
2. Updated to **Ion-Kit 1.9.2** to resolve contamination issues.

### Update 2024-08-06:
1. Added `.mp4` option for saving video files.
2. Updated to **Ion-Kit 1.9.x** with the group ID now saved in the config JSON file.

### Update 2024-07-29:
1. When recording, saving, or converting, display `output/yyyy-mm-dd-hh-ss` instead of just `output`.
2. Added zoom in/out functionality for resizing the preview window, replacing the previous crop behavior.

### Update 2024-06-14:
1. Added `.raw` option for image saving.
2. Instead of saving in the 'output' folder, images are now saved in a folder structure based on the timestamp `YYYYMMDDHHmmSS` as follows (tentatively using `group0` for GUI numbering):
    ```
    yyyy-mm-dd-hh-mm-ss/group0/camera0/.raw /.png /.bmp /.jpg /.wav (audio) /.mpg (video) /.txt (meta) /.bin (meta)
    yyyy-mm-dd-hh-mm-ss/group0/camera1/.raw
    yyyy-mm-dd-hh-mm-ss/group1/camera0/.raw
    yyyy-mm-dd-hh-mm-ss/group1/camera1/.raw
    ```
### Update 2024-06-06:
1. Integrated the start/stop button 

### Update 2024-05-09:
1. Fixed frame count and updated to **Ion-Kit 1.8.2**.

### Update 2024-04-10:
1. Separated the control panel and display windows.

### Update 2024-04-04:
1. Display images in Bayer format.
2. Renamed window titles.

### Update 2024-03-27:
1. Added simulation mode.

### Update 2024-03-21:
1. Made components resizable.

### Update 2024-03-06:
1. Added options for saving images in formats: `.bin`, `.jpg`, `.png`, and `.bmp` (order does not matter).
2. Renamed buttons to **Start Saving** and **Stop Saving**.
3. Disabled (grayed out) the **Stop Saving** button when the user clicks **Start Saving** with a specified time duration (from the text box).
4. When switching modes in Gendc, the bottom-left corner now displays the exact mode name.