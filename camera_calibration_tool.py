import traceback

import cv2
from ionpy import Node, Builder, Buffer, Port, Param, Type, TypeCode
import numpy as np
from PIL import Image
from PIL import ImageTk
import tkinter as tk

from utils import log_write, get_bb_for_obtain_image, get_bit_width, required_bit_depth, get_num_bit_shift
from utils import DEFAULT_PREFIX_NAME1, DEFAULT_PREFIX_NAME0, DEFAULT_GENDC_PREFIX_NAME0, DEFAULT_GENDC_PREFIX_NAME1

import queue

q = queue.Queue()

MAX_BUF_SIZE = 50
def clear_queue():
    q.queue.clear()
    


class FrameCapture:
    def __init__(self, dev_info, test_info):

        self.dev_info, self.test_info = dev_info, test_info
        self.sim_mode = False
        self.is_sync = False
        self.is_realtime = True
        self.gains = dev_info[dev_info["Gain Key"]]
        self.exposuretimes = dev_info[dev_info["ExposureTime Key"]]

        if test_info["Simulation Mode"]:
            self.sim_mode = True
        else:
            self.is_sync = test_info["Frame Sync Mode"]
            self.is_realtime = test_info["Realtime Display Mode"]

        self.gendc_mode = False
        self.stop = False
        self.start_save = False
        self.output_directories = [test_info["Default Directory"]] * dev_info["Number of Devices"]

        self.exclude = False


    def run(self):
        try:
            self.start_save = False
            width = self.dev_info["Width"]
            height = self.dev_info["Height"]
            payloadsizes = self.dev_info["PayloadSize"]
            ratio = height / width
            wp = Port("width", Type(TypeCode.Int, 32, 1), 0)
            hp = Port("height", Type(TypeCode.Int, 32, 1), 0)

            wp.bind(width)
            hp.bind(height)

            num_device = self.dev_info["Number of Devices"]

            pixelformat = self.dev_info["PixelFormat"]
            # the following items varies by PixelFormat
            depth_of_buffer = required_bit_depth(pixelformat)
            data_type = np.uint8 if depth_of_buffer == 8 else np.uint16

            # set params
            frame_sync = Param("frame_sync", self.is_sync)
            realtime_display_mode = Param("realtime_display_mode", self.is_realtime)
            enable_control = Param("enable_control", True)
            gain_key = Param("gain_key", self.dev_info["Gain Key"])
            exposure_key = Param("exposure_key", self.dev_info["ExposureTime Key"])

            gain_ps = []
            exposure_ps = []
            payloadsize_ps = []

            for i in range(num_device):
                gain_ps.append(Port("gain" + str(i), Type(TypeCode.Float, 64, 1), 0))
                exposure_ps.append(Port("exposure" + str(i), Type(TypeCode.Float, 64, 1), 0))
                payloadsize_ps.append(Port("payloadsize" + str(i), Type(TypeCode.Int, 32, 1), 0))

            bb_name = get_bb_for_obtain_image(num_device, pixelformat)

            builder = Builder()
            builder.set_target("host")
            builder.with_bb_module("ion-bb")

            # set params
            num_devices = Param("num_devices", str(num_device))

            if self.sim_mode:
                node = builder.add(bb_name).set_params([num_devices,
                                                        Param("pixel_format", pixelformat),
                                                        Param("width", width), Param("height", height),
                                                        Param("force_sim_mode", True),
                                                        ])
            else:
                # add a node to pipeline
                node = builder.add(bb_name).set_iports([gain_ps[0], exposure_ps[0]]) \
                    .set_params(
                    [num_devices, frame_sync, realtime_display_mode, enable_control, gain_key,
                     exposure_key]) if num_device == 1 \
                    else builder.add(bb_name) \
                    .set_iports([gain_ps[0], exposure_ps[0], gain_ps[1], exposure_ps[1]]) \
                    .set_params(
                    [num_devices, frame_sync, realtime_display_mode, enable_control, gain_key, exposure_key])

            display_bi_p = node.get_port("output")

            # create halide buffer for output port
            img_outputs = []
            img_outputs_data = []
            img_output_size = (height, width,)

            # set I/O ports
            for i in range(num_device):
                # input
                gain_ps[i].bind(self.gains[i])
                exposure_ps[i].bind(self.exposuretimes[i])
                payloadsize_ps[i].bind(payloadsizes[i])
                # output
                img_outputs_data.append(np.full(img_output_size, fill_value=0, dtype=data_type))
                img_outputs.append(Buffer(array=img_outputs_data[i]))

            display_bi_p.bind(img_outputs)

            # create halide buffer for output port
            gendc_outputs = []
            gendc_outputs_data = []
            for i in range(num_device):
                # input
                gendc_outputs_data.append(np.full((payloadsizes[i],), fill_value=0, dtype=np.uint8))
                gendc_outputs.append(Buffer(array=gendc_outputs_data[i]))

            # create halide buffer for terminator saver building block
            t = Type(TypeCode.Int, 32, 1)
            out0 = Buffer(t, ())
            out1 = Buffer(t, ())

            is_display = True

            while not self.stop:
                builder.run()
                # save gendc
                if self.start_save and self.gendc_mode:
                    q.put((gendc_outputs_data, True))
                # save image or previewing
                else:
                    q.put((img_outputs_data, False))

                if self.start_save and is_display:
                    is_display = False
                    # clear_queue()
                    builder = Builder()
                    builder.set_target("host")
                    builder.with_bb_module("ion-bb")
                    if not self.gendc_mode:
                        # add 1st node to pipeline
                        if self.sim_mode:
                            node = builder.add(bb_name).set_params([num_devices,
                                                                    Param("pixel_format", pixelformat),
                                                                    Param("width", width), Param("height", height),
                                                                    Param("force_sim_mode", True),
                                                                    ])
                        else:
                            node = builder.add(bb_name) \
                                .set_iports([gain_ps[0], exposure_ps[0]]) \
                                .set_params(
                                [num_devices, frame_sync,
                                 Param("realtime_display_mode", False),
                                 enable_control, gain_key, exposure_key]) if num_device == 1 \
                                else builder.add(bb_name) \
                                .set_iports([gain_ps[0], exposure_ps[0], gain_ps[1], exposure_ps[1]]) \
                                .set_params(
                                [num_devices, frame_sync,
                                 Param("realtime_display_mode", False),
                                 enable_control, gain_key, exposure_key])

                        device_ps = node.get_port("device_info")
                        frame_ps = node.get_port("frame_count")

                        display_bi_p = node.get_port("output")
                        display_bi_p.bind(img_outputs)

                        t_node0 = builder.add("image_io_binarysaver_u{}x2".format(depth_of_buffer)) \
                            .set_iports([node.get_port("output")[0], device_ps[0], frame_ps[0], wp, hp, ]) \
                            .set_params(
                            [Param("output_directory", self.output_directories[0]),
                             Param("prefix", DEFAULT_PREFIX_NAME0)])

                        terminator0 = t_node0.get_port("output")
                        terminator0.bind(out0)

                        if num_device == 2:
                            t_node1 = builder.add("image_io_binarysaver_u{}x2".format(depth_of_buffer)) \
                                .set_iports([node.get_port("output")[1], device_ps[1], frame_ps[1], wp, hp, ]) \
                                .set_params(
                                [Param("output_directory", self.output_directories[1]),
                                 Param("prefix", DEFAULT_PREFIX_NAME1)])
                            terminator1 = t_node1.get_port("output")
                            terminator1.bind(out1)
                    else:
                        builder = Builder()
                        builder.set_target("host")
                        builder.with_bb_module("ion-bb")

                        if self.sim_mode:
                            node = builder.add("image_io_u3v_gendc").set_params([num_devices,
                                                                                 Param("pixel_format", pixelformat),
                                                                                 Param("width", width),
                                                                                 Param("height", height),
                                                                                 Param("force_sim_mode", True),
                                                                                 ])
                        else:
                            node = builder.add("image_io_u3v_gendc").set_iports([gain_ps[0], exposure_ps[0]]) \
                                .set_params(
                                [num_devices, frame_sync, Param("realtime_display_mode", False), enable_control,
                                 gain_key,
                                 exposure_key]) if num_device == 1 \
                                else builder.add("image_io_u3v_gendc") \
                                .set_iports([gain_ps[0], exposure_ps[0], gain_ps[1], exposure_ps[1]]) \
                                .set_params(
                                [num_devices, frame_sync, Param("realtime_display_mode", False), enable_control,
                                 gain_key,
                                 exposure_key])

                        gendc_p = node.get_port("gendc")
                        gendc_p.bind(gendc_outputs)
                        t_node0 = builder.add("image_io_binary_gendc_saver") \
                            .set_iports(
                            [node.get_port("gendc")[0], node.get_port("device_info")[0], payloadsize_ps[0], ]) \
                            .set_params(
                            [Param("output_directory", self.output_directories[0]),
                             Param("prefix", DEFAULT_GENDC_PREFIX_NAME0)])
                        terminator0 = t_node0.get_port("output")
                        terminator0.bind(out0)
                        if num_device == 2:
                            t_node1 = builder.add("image_io_binary_gendc_saver") \
                                .set_iports(
                                [node.get_port("gendc")[1], node.get_port("device_info")[1], payloadsize_ps[1], ]) \
                                .set_params(
                                [Param("output_directory", self.output_directories[1]),
                                 Param("prefix", DEFAULT_GENDC_PREFIX_NAME1)])
                            terminator1 = t_node1.get_port("output")
                            terminator1.bind(out1)
                    builder.run()
                    self.exclude = True

                elif not self.start_save and not is_display:
                    is_display = True
                    # clear_queue()
                    builder = Builder()
                    builder.set_target("host")
                    builder.with_bb_module("ion-bb")

                    # add first node to pipeline
                    if self.sim_mode:
                        node = builder.add(bb_name).set_params([num_devices,
                                                                Param("pixel_format", pixelformat),
                                                                Param("width", width), Param("height", height),
                                                                Param("force_sim_mode", True),
                                                                ])
                    else:
                        node = builder.add(bb_name) \
                            .set_iports([gain_ps[0], exposure_ps[0]]) \
                            .set_params(
                            [num_devices, frame_sync, realtime_display_mode, enable_control, gain_key,
                             exposure_key]) if num_device == 1 \
                            else builder.add(bb_name) \
                            .set_iports([gain_ps[0], exposure_ps[0], gain_ps[1], exposure_ps[1]]) \
                            .set_params(
                            [num_devices, frame_sync, realtime_display_mode, enable_control, gain_key, exposure_key])

                    display_bi_p = node.get_port("output")
                    display_bi_p.bind(img_outputs)

                # set the gain and exposure each run
                for i in range(num_device):
                    gain_ps[i].bind(self.gains[i])
                    exposure_ps[i].bind(self.exposuretimes[i])
        except Exception as e:
            log_write("Error", traceback.format_exc())
        finally:
            clear_queue()  # empty the stream


def resize(ori, ratio: int, cur_width: int, cur_height: int) -> np.ndarray:
    if cur_width / cur_height < ratio:
        resized_width = cur_width
        resized_height = int(resized_width / ratio)
    else:
        resized_height = cur_height
        resized_width = int(resized_height * ratio)

    new = cv2.resize(ori, (resized_width, resized_height))
    return new


class Display:
    def __init__(self, dev_info, test_info):

        self.dev_info, self.test_info = dev_info, test_info

        self.stop = False
        self.panel0 = None
        self.panel1 = None

        self.is_redirected = False  # True only when saving - > display or display -> saving

        ## 3D image processing
        self.r_gains = test_info["Red Gains"]
        self.b_gains = test_info["Blue Gains"]
        self.g_gains = test_info["Green Gains"]

    def _display(self, master, root0, display_frame0, root1=None, display_frame1=None):
        try:
            if self.test_info["Color Display Mode"]:
                self._display_3d(display_frame0, display_frame1, root0, root1)
            else:
                self._display_2D(display_frame0, display_frame1, root0, root1)

            if self.stop:
                root0.quit()
                if root1 is not None:
                    root1.quit()
        except Exception as e:
            log_write("ERROR", "Previewing error: {}".format(traceback.format_exc()))

    def _display_2D(self, display_frame0, display_frame1, root0, root1):
        num_device = self.dev_info["Number of Devices"]
        pixelformat = self.dev_info["PixelFormat"]
        width = self.dev_info["Width"]
        height = self.dev_info["Height"]
        ratio = width / height
        data_type = np.uint8 if required_bit_depth(pixelformat) == 8 else np.uint16
        depth_of_buffer = np.iinfo(data_type).bits
        frames = [None] * 2
        descriptor_sizes = []
        num_bit_shift = get_num_bit_shift(pixelformat)
        coef = pow(2, num_bit_shift)

        for i in range(num_device):
            descriptor_sizes.append(self.dev_info["PayloadSize"][i] - self.dev_info["Width"] * self.dev_info[
                "Height"] * depth_of_buffer // 8)  # specifically design for v1.2

        while not self.stop:
            if self.is_redirected:
                self.is_redirected = False
                clear_queue()  # empty the stream
            elif q.qsize() > MAX_BUF_SIZE:
                clear_queue()

            try:
                binary_outputs_data, is_GenDC = q.get(block=False)  # don't block
            except queue.Empty:
                continue
            if is_GenDC:
                # to do
                for i in range(num_device):
                    frame = np.frombuffer(binary_outputs_data[i].tobytes()[descriptor_sizes[i]:], dtype=data_type)
                    frame_copy = np.array(frame.reshape(height, width))
                    frame_copy = frame_copy * coef
                    if depth_of_buffer == 8:
                        frames[i] = frame_copy.astype("uint8")
                    else:
                        frames[i] = (frame_copy / 256).astype("uint8")
            else:
                for i in range(num_device):
                    frame = binary_outputs_data[i]
                    frame = frame * coef
                    if depth_of_buffer == 8:
                        frames[i] = frame.astype("uint8")
                    else:
                        frames[i] = (frame / 256).astype("uint8")

            frame0 = frames[0]

            # resize image according to window size here
            cur_width = root0.winfo_width()
            cur_height = root0.winfo_height()
            root0.geometry("{}x{}".format(cur_width, cur_height))
            frame0 = resize(frame0, ratio, cur_width, cur_height)
            image0 = ImageTk.PhotoImage(Image.fromarray(frame0))
            if self.panel0 is None:
                self.panel0 = tk.Label(master=display_frame0, image=image0)
                self.panel0.image = image0
                self.panel0.pack(fill="both")
            # otherwise, simply update the panel
            else:
                self.panel0.configure(image=image0)
                self.panel0.image = image0

            # if the panel is not None, we need to initialize it
            if num_device == 2:
                frame1 = frames[1]
                # resize image according to window size here
                cur_width = root1.winfo_width()
                cur_height = root1.winfo_height()
                root1.geometry("{}x{}".format(cur_width, cur_height))
                frame1 = resize(frame1, ratio, cur_width, cur_height)

                image1 = ImageTk.PhotoImage(Image.fromarray(frame1))
                if self.panel1 is None:
                    self.panel1 = tk.Label(master=display_frame1, image=image1)
                    self.panel1.image = image1
                    self.panel1.pack(fill="both")
                # otherwise, simply update the panel
                else:
                    self.panel1.configure(image=image1)
                    self.panel1.image = image1

    def _display_3d(self, display_frame0, display_frame1, root0, root1):
        # is is better to use opencv?
        width = self.dev_info["Width"]
        height = self.dev_info["Height"]
        ratio = width / height
        num_device = self.dev_info["Number of Devices"]
        pixelformat = self.dev_info["PixelFormat"]

        # set I/O port
        wp = Port("width", Type(TypeCode.Int, 32, 1), 0)
        hp = Port("height", Type(TypeCode.Int, 32, 1), 0)
        wp.bind(width)
        hp.bind(height)
        # the following items varies by PixelFormat
        data_type = np.uint8 if required_bit_depth(pixelformat) == 8 else np.uint16
        depth_of_buffer = np.iinfo(data_type).bits
        r_gain_ports = []
        g_gain_ports = []
        b_gain_ports = []
        for i in range(num_device):
            r_gain_ports.append(Port("r_gain" + str(i), Type(TypeCode.Float, 32, 1), 0))
            g_gain_ports.append(Port("g_gain" + str(i), Type(TypeCode.Float, 32, 1), 0))
            b_gain_ports.append(Port("b_gain" + str(i), Type(TypeCode.Float, 32, 1), 0))
        builder = Builder()
        builder.set_target('host')
        builder.with_bb_module('ion-bb')
        input_ports = []
        display_color_ports = []
        for i in range(num_device):
            input_ports.append(Port("input{}".format(i), Type(TypeCode.Uint, depth_of_buffer, 1), 2))
        for i in range(num_device):
            image_p = input_ports[i]
            if depth_of_buffer == 8:
                node = builder.add("base_cast_2d_uint8_to_uint16") \
                    .set_iports([image_p])
                image_p = node.get_port("output")

            node = builder.add("image_processing_normalize_raw_image") \
                .set_iports([image_p]) \
                .set_params([Param("bit_width", get_bit_width(pixelformat)),
                             Param("bit_shift", 0)])

            node = builder.add("image_processing_bayer_demosaic_linear").set_iports([node.get_port("output")]) \
                .set_params([Param("bayer_pattern", self.test_info["Color Pattern"]), Param("width", width),
                             Param("height", height)])  # Bayer to BGR

            node = builder.add("base_denormalize_3d_uint8") \
                .set_iports([node.get_port("output")])

            node = builder.add("image_processing_reorder_color_channel_3d_uint8").set_iports([node.get_port("output")]) \
                .set_params([Param("color_dim", 2)])  # BGR to RGB

            node = builder.add("image_processing_color_dynamic_adjustment") \
                .set_iports([
                b_gain_ports[i],
                g_gain_ports[i],
                r_gain_ports[i],
                node.get_port("output")])  # output(x, y, c)

            node = builder.add("base_reorder_buffer_3d_uint8") \
                .set_iports([node.get_port("output")]) \
                .set_params([
                Param("dim0", "2"),
                Param("dim1", "0"),
                Param("dim2", "1"),
            ])  # output(c, x, y)
            display_color_p = node.get_port("output")
            display_color_ports.append(display_color_p)
        # display_color_p0 = display_color_ports[0]
        # display_color_p1 = display_color_ports[1]
        rgb_outputs_data = []
        rgb_outputs = []
        binary_input_data = []
        binary_inputs = []
        for i in range(num_device):
            r_gain_ports[i].bind(self.r_gains[i])
            g_gain_ports[i].bind(self.g_gains[i])
            b_gain_ports[i].bind(self.b_gains[i])
        for i in range(num_device):
            rgb_outputs_data.append(np.full((height, width, 3), fill_value=0, dtype=np.uint8))
            rgb_outputs.append(Buffer(array=rgb_outputs_data[i]))
        for i in range(num_device):
            binary_input_data.append(np.full((height, width), fill_value=0, dtype=data_type))
            binary_inputs.append(Buffer(array=binary_input_data[i]))
            display_color_ports[i].bind(rgb_outputs[i])
            input_ports[i].bind(binary_inputs[i])

        descriptor_sizes = []
        for i in range(num_device):
            descriptor_sizes.append(self.dev_info["PayloadSize"][i] - self.dev_info["Width"] * self.dev_info[
                "Height"] * depth_of_buffer // 8)  # specifically design for v1.2

        while not self.stop:
            if self.is_redirected:
                self.is_redirected = False
                clear_queue()  # empty the stream
            elif q.qsize() > MAX_BUF_SIZE:
                clear_queue()

            try:
                binary_outputs_data, is_GenDC = q.get(block=False)  # don't block
            except queue.Empty:
                continue

            if is_GenDC:
                for i in range(num_device):
                    # to do
                    binary_output_image_data = np.frombuffer(binary_outputs_data[i].tobytes()[descriptor_sizes[i]:],
                                                             dtype=data_type)
                    np.copyto(binary_input_data[i], binary_output_image_data.reshape(height, width))

            else:
                for i in range(num_device):
                    np.copyto(binary_input_data[i], binary_outputs_data[i])
            builder.run()
            for i in range(num_device):
                r_gain_ports[i].bind(self.r_gains[i])
                g_gain_ports[i].bind(self.g_gains[i])
                b_gain_ports[i].bind(self.b_gains[i])

            frame0 = rgb_outputs_data[0]

            cur_width = root0.winfo_width()
            cur_height = root0.winfo_height()
            root0.geometry("{}x{}".format(cur_width, cur_height))
            frame0 = resize(frame0, ratio, cur_width, cur_height)

            image0 = ImageTk.PhotoImage(Image.fromarray(frame0))
            if self.panel0 is None:
                self.panel0 = tk.Label(master=display_frame0, image=image0)
                self.panel0.image = image0
                self.panel0.pack(fill="both")
            # otherwise, simply update the panel
            else:
                self.panel0.configure(image=image0)
                self.panel0.image = image0

            # if the panel is not None, we need to initialize it
            if num_device == 2:
                frame1 = rgb_outputs_data[1]
                cur_width = root1.winfo_width()
                cur_height = root1.winfo_height()

                root1.geometry("{}x{}".format(cur_width, cur_height))
                frame1 = resize(frame1, ratio, cur_width, cur_height)
                image1 = ImageTk.PhotoImage(Image.fromarray(frame1))
                if self.panel1 is None:
                    self.panel1 = tk.Label(master=display_frame1, image=image1)
                    self.panel1.image = image1
                    self.panel1.pack(fill="both")
                # otherwise, simply update the panel
                else:
                    self.panel1.configure(image=image1)
                    self.panel1.image = image1

    def run(self, master, root0, display_frame0, root1=None, display_frame1=None):
        self._display(master, root0, display_frame0, root1, display_frame1)
