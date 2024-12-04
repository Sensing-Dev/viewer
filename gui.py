from __future__ import print_function

import datetime
import os
import json
from ttkbootstrap.constants import *
from tkinter import ttk
from tkinter import filedialog
from tkinter import *
import tkinter as tk
import threading
from camera_calibration_tool import Display, FrameCapture
from utils import set_commandline_options, get_device_info, log_write
import time
from convert import Converter

IPAD_X = 10
IPAD_Y = 10


class U3VCameraGUI:
    def __init__(self, master, settings):
        # store the video stream object and output path, then initialize
        # the most recently read frame, thread for reading frames, and
        # the thread stop event

        self.button_on_save = True
        dev_info, test_info = get_device_info(settings)
        self.display = Display(dev_info, test_info)
        self.capture = FrameCapture(dev_info, test_info)
        self.converter = Converter(dev_info, test_info)

        # initialize the sub window and image panel
        self.master = master

        self.is_gendc_mode = test_info["Gendc Mode"]
        self.capture.gendc_mode = self.is_gendc_mode

        self.img_width = dev_info['Width']
        self.img_height = dev_info['Height']

        self.thread_pool = []

        # start a thread that constantly pools the video sensor for
        # the most recently read frame

        self.quit = False
        self.stop_save = False
        self.display_frames = []
        self.roots = []

        gain_values = []
        exposure_time_values = []
        r_gain_values = []
        b_gain_values = []
        g_gain_values = []

        self.num_device = dev_info["Number of Devices"]
        self.pixel_format = dev_info["PixelFormat"]

        self.fps = dev_info["FrameRate"]
        self.exposuretime_max = dev_info["ExposureTime Max"]

        default_directory = test_info["Default Directory"]
        winfos = test_info["Window infos"]
        for i in range(self.num_device):
            self.roots.append(Toplevel(self.master))
            root = self.roots[i]
            root.title(dev_info["DeviceModelNames"][i])
            root.protocol("WM_DELETE_WINDOW", self.onClose)
            self.display_frames.append(tk.Frame(self.roots[i]))
            self.display_frames[i].pack(fill=BOTH, expand=True, padx=10, pady=5, )
            root.geometry('{}x{}'.format(winfos[2*i], winfos[2*i+1]))

        self.control_root = Toplevel(self.master)
        self.control_root.protocol("WM_DELETE_WINDOW", self.onClose)
        self.control_root.title("Control Panel")
        self.control_root.minsize(640, 800)
        config_frame = tk.Frame(self.control_root)

        for i in range(self.num_device):
            # slider current value
            time_label = ttk.Label(config_frame, text=dev_info["DeviceModelNames"][i])
            time_label.pack(pady=10)

            r_gain_values.append(tk.DoubleVar(value=self.display.r_gains[i]))
            b_gain_values.append(tk.DoubleVar(value=self.display.b_gains[i]))
            g_gain_values.append(tk.DoubleVar(value=self.display.g_gains[i]))
            gain_values.append(tk.DoubleVar(value=self.capture.gains[i]))
            exposure_time_values.append(tk.DoubleVar(value=self.capture.exposuretimes[i]))

            # mainframe = tk.Frame(self.root)
            self.add_slider(i, tk.Frame(config_frame), gain_values[i], text="gain ", channel='all', increment=1,
                            from_=dev_info["Gain Min"], to=dev_info["Gain Max"])
            self.add_slider(i, tk.Frame(config_frame), r_gain_values[i], text="r gain", channel='r', from_=0, to=3)
            self.add_slider(i, tk.Frame(config_frame), g_gain_values[i], text="g gain", channel='g', from_=0, to=3)
            self.add_slider(i, tk.Frame(config_frame), b_gain_values[i], text="b gain", channel='b', from_=0, to=3)
            self.add_slider(i, tk.Frame(config_frame), exposure_time_values[i], text="exposure time\n(μs)", increment=1,
                            from_=dev_info["ExposureTime Min"], to=dev_info["ExposureTime Max"])

        config_option_frame = tk.Frame(config_frame)

        time_label = ttk.Label(config_option_frame, text="extension")
        time_label.grid(column=0, row=0, sticky="e", padx=5, pady=5, )

        combo = ttk.Combobox(config_option_frame,
                             state="readonly",
                             values=["bin", "bmp", "jpg", "jpeg", "png", "raw", "mp4"],
                             width=5
                             )
        combo.current(2)
        combo.grid(column=1, row=0, sticky="we", pady=5, )
        self.combo = combo

        self.delete_bin = tk.BooleanVar(value=test_info["Delete Bins"])
        self.testCheck = tk.Checkbutton(config_option_frame, variable=self.delete_bin, justify=LEFT, text="delete bin")
        self.testCheck.grid(column=2, row=0, sticky="w", pady=5, )

        time_label = ttk.Label(config_option_frame, text="time duration(s):", width=15, anchor="e")
        time_label.grid(column=3, row=0, sticky="e", padx=5, pady=5, )

        time_range = tk.IntVar(value=0)
        time_entry = ttk.Entry(config_option_frame, textvariable=time_range)
        time_entry.grid(column=4, row=0, sticky="w", padx=5, pady=5, )

        config_option_frame.columnconfigure(0, weight=1)
        config_option_frame.columnconfigure(1, weight=1)
        config_option_frame.columnconfigure(2, weight=1)
        config_option_frame.columnconfigure(3, weight=2)
        config_option_frame.columnconfigure(4, weight=2)

        folderPath = StringVar(value=default_directory)

        progress_frame = tk.Frame(config_frame)
        btnFind = ttk.Button(progress_frame, text="Browse Folder", width=15,
                             command=lambda folderPath=folderPath: self.getfolderPath(folderPath))
        btnFind.grid(column=0, row=0, sticky="e", padx=5, pady=5, )

        folder_entry = ttk.Label(progress_frame, textvariable=folderPath, )
        folder_entry.grid(column=1, row=0, sticky='we', padx=5, pady=5, )

        save_btn = ttk.Button(progress_frame, text="Start Saving", width=15, bootstyle=INFO,
                              command=lambda folderPath=folderPath: self.onSave(folderPath))
        save_btn.grid(column=0, row=1, sticky='e', padx=5, pady=5, )
        self.save_btn = save_btn

        progressBar = ttk.Progressbar(progress_frame, mode="determinate", orient='horizontal',
                                      maximum=100, value=0, length=300)
        progressBar.grid(column=1, row=1, sticky='we', padx=5, pady=5, )

        self.progressBar = progressBar
        self.time_entry = time_entry
        self.time_range = time_range

        self.save_folder_path = StringVar()
        sensor_folder_label = ttk.Label(progress_frame, text="Output Folder", width=15,
                                        anchor="center")
        sensor_folder_label.grid(column=0, row=2, sticky='e', ipadx=5, ipady=5, padx=5, pady=5, )

        sensor_folder_entry = ttk.Label(progress_frame, textvariable=self.save_folder_path, )
        sensor_folder_entry.grid(column=1, row=2, sticky='we', padx=5, pady=5, )

        progress_frame.columnconfigure(0, weight=1)
        progress_frame.columnconfigure(1, weight=3)

        # sensor1_folder_entry = ttk.Label(progress_frame, textvariable=save_folder_path1 )
        # sensor1_folder_entry.grid(column=1, row=3, sticky='we', padx=5, pady=2, )

        config_option_frame.pack(fill=BOTH, expand=True)
        progress_frame.pack(fill=BOTH, expand=True)
        config_frame.pack(fill=BOTH, expand=True, )

        if self.is_gendc_mode:
            mode = ttk.Label(self.control_root, text="Gendc Mode: ON", bootstyle="success-inversed", padding=5)
        else:
            mode = ttk.Label(self.control_root, text="Gendc Mode: OFF", bootstyle="success-inversed", padding=5)
        mode.pack(side="left", padx=5, pady=5, )

        quit_btn = ttk.Button(self.control_root, text="Quit ", width=10, bootstyle=DANGER, command=self.onClose)
        quit_btn.pack(side="right", padx=5, pady=5, )
        gend_btn = ttk.Button(self.control_root, text="Switch Mode", width=15, bootstyle=INFO,
                              command=lambda mode=mode: self.onRedirect(mode))
        gend_btn.pack(side="right", padx=5, pady=5, )

        if not dev_info["GenDCStreamingMode"]:
            gend_btn.configure(state="disabled")

        capture_t = threading.Thread(target=self.capture.run)
        capture_t.start()
        self.thread_pool.append(capture_t)

        if self.num_device == 2:
            display_t = threading.Thread(target=self.display.run,
                                         args=(self.master, self.roots[0], self.display_frames[0], self.roots[1],
                                               self.display_frames[1]))
        else:
            display_t = threading.Thread(target=self.display.run,
                                         args=(self.master, self.roots[0], self.display_frames[0]))

        display_t.start()
        self.thread_pool.append(display_t)

    def getfolderPath(self, folderPath):
        folder_selected = filedialog.askdirectory()
        folderPath.set(folder_selected)

    def add_slider(self, idx, mainframe,
                   value,
                   text,
                   channel=None,
                   from_=0.0,
                   to=48.0,
                   increment=0.1
                   ):

        def update_value(event=None):
            if channel == 'r':
                set_value = max(0, min(round(value.get(), 2), to))
                self.display.r_gains[idx] = set_value
            elif channel == 'b':
                set_value = max(0, min(round(value.get(), 2), to))
                self.display.b_gains[idx] = set_value
            elif channel == 'g':
                set_value = max(0, min(round(value.get(), 2), to))
                self.display.g_gains[idx] = set_value
            elif channel == 'all':
                set_value = max(0, min(round(value.get()), to))
                self.capture.gains[idx] = set_value
            else:
                set_value = max(0, min(round(value.get(), 2), to))
                self.capture.exposuretimes[idx] = set_value
            set_value = '{: .1f}'.format(set_value)
            value.set(set_value)
            value_label.configure(text=value.get())

        # label for the slider

        slider_label = ttk.Label(mainframe, text=text + ': ', width=15, justify=CENTER, anchor=CENTER)
        slider_label.grid(column=0, row=0, sticky='e')

        #  slider
        slider = ttk.Scale(mainframe, from_=from_, to=to, orient='horizontal', command=update_value,
                           variable=value)

        spin = ttk.Spinbox(mainframe, textvariable=value, width=10, from_=from_,
                           to=to, increment=increment, command=update_value, )

        spin.bind("<Return>", update_value)

        slider.grid(column=1, row=0, sticky='we', padx=10)
        spin.grid(column=2, row=0, sticky='w', padx=10)
        # value label
        value_label = ttk.Label(mainframe, text=value.get(), )
        value_label.grid(row=2, columnspan=2, sticky='n')

        mainframe.columnconfigure(0, weight=1, )
        mainframe.columnconfigure(1, weight=4, )
        mainframe.columnconfigure(2, weight=1, )
        mainframe.rowconfigure(0, weight=1, )
        mainframe.rowconfigure(1, weight=1, )

        mainframe.pack(fill=BOTH, expand=True)

    def onRedirect(self, mode):
        # set the stop event, cleanup the camera, and allow the rest of
        # the quit process to continue
        if not self.is_gendc_mode:  # redirect to Gendc
            mode.configure(text="Gendc Mode: ON", bootstyle="info-inversed")
            log_write("USER CONTROL", "Redirect to GenDC Mode: ON")
        else:  # redirect to Display
            mode.configure(text="Gendc Mode: OFF", bootstyle="success-inversed")
            log_write("USER CONTROL", "Redirect to GenDC Mode: OFF")
        self.is_gendc_mode = not self.is_gendc_mode
        self.capture.gendc_mode = not self.capture.gendc_mode

    def reenable_button(self):
        self.save_btn.configure(state='normal')
        self.save_btn.config(text='start saving')

    def converting_state_on_button(self):
        self.save_btn.configure(state='disabled')
        self.save_btn.config(text='Converting')

    def onSave(self, folderPath):
        # save either gendc or image
        def update_progress():
            try:
                self.progressBar['value'] = 0
                if save_time > 0:
                    while True:
                        if self.capture.exclude:
                            self.save_btn.config(text='Saving')
                            for i in range(save_time):
                                if self.quit or self.stop_save:
                                    break
                                self.progressBar['value'] += 100 / save_time
                                time.sleep(1)
                            break
                    self.capture.exclude = False
                else:
                    while not self.quit and not self.stop_save:
                        self.progressBar['value'] = 0
                        if self.capture.exclude:
                            self.save_btn.config(text='Stop Saving')
                            self.capture.exclude = False

                self.capture.start_save = False
                self.stop_save = False
                self.display.is_redirected = True  # saving -> display

                self.progressBar['value'] = 100
                self.master.after(0, self.converting_state_on_button)
                if extension == "mp4":
                    self.converter.convert_to_video(self.capture.output_directories, self.is_gendc_mode,
                                                    r_gains=self.display.r_gains,
                                                    g_gains=self.display.g_gains,
                                                    b_gains=self.display.b_gains,
                                                    to_delete=self.delete_bin.get())
                elif extension != "bin":
                    self.converter.convert_to_img(self.capture.output_directories, self.is_gendc_mode,
                                                  r_gains=self.display.r_gains,
                                                  g_gains=self.display.g_gains,
                                                  b_gains=self.display.b_gains,
                                                  extension=extension, to_delete=self.delete_bin.get())
            except Exception as e:
                print(e)
            finally:
                self.progressBar['value'] = 0
                # after saving, enable start button
                self.master.after(0, self.reenable_button)

        if self.button_on_save:  # start saving
            folder = folderPath.get()
            current_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
            if folder == '':
                tk.messagebox.showerror(title="Error",
                                        message="Output directory is empty, please use Browse Folder to specify the output directory")
                return
            try:
                save_time = self.time_range.get()
            except Exception as e:
                self.time_range.set(0)
                tk.messagebox.showerror(title="Error",
                                        message="Please input int value in the input time duration entry")
                return

            for i in range(self.num_device):
                save_directory = os.path.join(folder, current_time, "group0", "camera" + str(i))
                self.capture.output_directories[i] = save_directory
                self.save_folder_path.set(os.path.join(folder, current_time))
                if not os.path.isdir(save_directory):
                    os.makedirs(save_directory)

            extension = self.combo.get()
            self.capture.start_save = True
            self.display.is_redirected = True  # display- > saving

            if save_time == 0:
                # self.stop_sav_btn.configure(state='active')
                self.button_on_save = not self.button_on_save  # save button becomes stop button
                self.save_btn.config(text='Pipelining')
                log_write("WARNING",
                          "GenDC Mode: {}, you don't define the time duration, please use stop save button to stop saving!".format(
                              self.is_gendc_mode))
            else:
                self.save_btn.configure(state='disabled')  # disabled save button, but nextime you click it is still save button
                self.save_btn.config(text='Pipelining')
                log_write("DEBUG", "GenDC Mode: {} , start saving for {} s".format(self.is_gendc_mode, save_time))

            self.time_range.set(0)
            update_t = threading.Thread(target=update_progress, args=())
            update_t.daemon = True
            update_t.start()

        else:  # stop saving
            self.stop_save = True
            self.capture.start_save = False
            self.button_on_save = not self.button_on_save  # stop button becomes save button
            self.display.is_redirected = True  # saving -> display

    def onClose(self):
        # set the stop event, cleanup the camera, and allow the rest of
        # the quit process to continue
        def check():
            while len(self.thread_pool) > 0:
                if not self.thread_pool[0].is_alive():
                    try:
                        self.thread_pool.pop(0)
                    except:
                        pass
            self.master.quit()

        def save_json():
            config = {
                "device number": self.num_device,
                "gains": self.capture.gains,
                "exposuretimes": self.capture.exposuretimes,
                "r_gains": self.display.r_gains,
                "g_gains": self.display.g_gains,
                "b_gains": self.display.b_gains,
                "gendc_mode": self.is_gendc_mode,
                "delete_bin": self.delete_bin.get(),
                "winfos": winfos,
####################        ADDITIONAL INFORMATION         ###########################
                "exposuretime max":  self.exposuretime_max,
                "fps": self.fps,
                "pixelformat": self.pixel_format
            }


            for i in range(self.num_device):
                with open('default.json', 'w') as f:
                    json.dump(config, f, indent=4, separators=(',', ': '))

        log_write("DEBUG", "Closing...")

        winfos = []

        for i in range(self.num_device):
            winfos.extend([self.roots[i].winfo_width(), self.roots[i].winfo_height()])

        self.capture.stop = True
        self.display.stop = True
        self.quit = True
        save_json()
        threading.Thread(target=check).start()


if __name__ == "__main__":
    # construct the argument parse and parse the arguments
    settings = set_commandline_options()
    root = tk.Tk()

    # initialize the video stream and allow the camera sensor to warmup

    cap = U3VCameraGUI(root, settings)

    # cap2 = U3VCameraGUI(root,settings)
    root.withdraw()
    root.mainloop()

    log_write("INFO", "Success.")
