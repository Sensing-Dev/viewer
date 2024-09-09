import json
import shutil
import time

import cv2
import numpy as np
from PIL import Image
import os
# Define width and height
from utils import log_write, required_bit_depth, get_num_bit_shift
from utils import PREFIX_NAME0, PREFIX_NAME1
from gendc_python.gendc_separator import descriptor as gendc

GDC_INTENSITY = 1


class Converter:
    def __init__(self, dev_info, test_info):
        self.dev_info, self.test_info = dev_info, test_info

    def convert_to_img(self, output_directories, is_gendc, extension, r_gains, g_gains, b_gains, to_delete=True,
                       rotate_limit=60, time_out=5):
        payloadsizes = self.dev_info["PayloadSize"]
        num_device = self.dev_info["Number of Devices"]
        pixelformat = self.dev_info["PixelFormat"]
        width = self.dev_info["Width"]
        height = self.dev_info["Height"]
        if extension == "bin" or extension not in ['bin', 'png', 'jpg', 'jpeg', 'png', 'bmp', 'raw']:
            log_write("ERROR", "extension {} is not supported".format(extension))
            return
        '''CONFIGURATION'''
        is_color = False
        if pixelformat.startswith("Bayer"):
            is_color = True
        num_bit_shift = get_num_bit_shift(pixelformat)
        required_bit = required_bit_depth(pixelformat)
        coef = pow(2, num_bit_shift)

        if extension != "bin":
            for i in range(num_device):
                output_directory = output_directories[i]
                payload_in_byte = payloadsizes[i]
                try:
                    file_list = [f for f in os.listdir(output_directory) if f.endswith(".bin")]  # exclude the json file
                    for file in file_list:
                        log_write("INFO", "Converting {} file into {}, please wait".format(file, extension))
                        file_path = os.path.join(output_directory, file)

                        if not is_gendc:
                            self.convert_single_img_bin_to_image(
                                file_path,
                                required_bit,
                                coef,
                                output_directory,
                                height, width, payload_in_byte, pixelformat,
                                is_color,
                                r_gains[i],
                                g_gains[i],
                                b_gains[i],
                                extension, rotate_limit=rotate_limit)
                        else:
                            self.convert_single_gendc_bin_to_image(
                                file_path,
                                required_bit,
                                coef,
                                output_directory,
                                height, width, payload_in_byte,
                                is_color,
                                r_gains[i],
                                g_gains[i],
                                b_gains[i],
                                extension, rotate_limit=rotate_limit)
                        if to_delete:
                            del_bin(file_path, time_out)

                except Exception as e:
                    log_write("Error", e)
                finally:
                    log_write("DEBUG", "Finish saving image in {}".format(output_directory))

        prefix_name0 = "gendc_0-" if is_gendc else PREFIX_NAME0
        prefix_name1 = "gendc_1-" if is_gendc else PREFIX_NAME1

        for i in range(num_device):
            output_directory = output_directories[i]
            if i == 0:
                sensor_info = read_config(os.path.join(output_directory, prefix_name0 + "config.json"), time_out)
            else:
                sensor_info = read_config(os.path.join(output_directory, prefix_name1 + "config.json"), time_out)
            if len(sensor_info) == 0:
                log_write("WARNING", "Cannot found config file")
                continue
            group_id = sensor_info["group_id"]
            log_write("DEBUG", "Group-id is {}".format(group_id))
            if group_id != 0:
                shutil.move(output_directory, output_directory.replace("group0", "group{}".format(group_id)))

    def convert_single_img_bin_to_image(self,
                                        file_path,
                                        required_bit,
                                        coef,
                                        output_directory,
                                        height, width, payload_in_byte, pixelformat,
                                        is_color,
                                        r_gain=1.0,
                                        g_gain=1.0,
                                        b_gain=1.0,
                                        extension="jpg", rotate_limit=60):
        cursor = 0
        img_size = width * height
        with open(file_path, mode='rb') as f:
            if required_bit_depth(pixelformat) == 8:
                d = np.fromfile(f, dtype=np.uint8)
            elif required_bit_depth(pixelformat) == 16:
                d = np.fromfile(f, dtype=np.uint16)
            else:
                log_write("Error", "PixelFormat: {} is not supported".format(self.pixelformat))
                return
            file_size_in_byte = len(d) * required_bit // 8
            offset = 0
            slide = 32 // required_bit
            for i in range(rotate_limit):
                if cursor >= file_size_in_byte:
                    break
                f.seek(cursor)
                frame_id = np.fromfile(f, dtype=np.uint32, count=1)
                cursor += 4
                offset += slide
                if len(frame_id) > 0:
                    frame_id = frame_id[0]
                else:
                    break
                img_arr = d[offset:offset + img_size]
                offset = offset + img_size
                cursor = cursor + payload_in_byte
                if img_arr.size == img_size:
                    if extension == 'raw':
                        img_arr.tofile(os.path.join(output_directory, str(frame_id) + "." + extension))
                    else:
                        img_arr = img_arr * coef
                        img_arr = img_arr.reshape((height, width))
                        if required_bit == 16 and extension != "png":
                            img_arr = (img_arr / 256).clip(0, 255).astype("uint8")  # convert to 8 bit 0 ~ 255
                        if is_color:
                            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_BayerBG2RGB)  # transfer Bayer to RGB
                            img_normalized = cv2.normalize(img_arr, None, 0, 1.0,
                                                           cv2.NORM_MINMAX, dtype=cv2.CV_32F)
                            (R, G, B) = cv2.split(img_normalized)
                            R = (R * r_gain).clip(0, 1)
                            G = (G * g_gain).clip(0, 1)
                            B = (B * b_gain).clip(0, 1)
                            img_float32 = cv2.merge([R, G, B])
                            img_arr = (img_float32 * 255).astype(np.uint8) # convert to 8 bit 0 ~ 255

                        # Make into PIL Image and save
                        PILimage = Image.fromarray(img_arr)
                        PILimage.save(os.path.join(output_directory, str(frame_id) + "." + extension))
                else:
                    log_write("Warning", "Incomplete image-{}".format(str(frame_id)))

    def convert_single_gendc_bin_to_image(self,
                                          file_path,
                                          required_bit,
                                          coef,
                                          output_directory,
                                          height, width, payload_in_byte,
                                          is_color,
                                          r_gain=1.0,
                                          g_gain=1.0,
                                          b_gain=1.0,
                                          extension="jpg", rotate_limit=60):
        cursor = 0
        with open(file_path, mode='rb') as f:
            filecontent = f.read()
            for i in range(rotate_limit):
                if cursor >= len(filecontent):
                    break
                try:
                    gendc_container = gendc.Container(filecontent[cursor:])
                    # get GenDC container information
                    # get first available image component
                    image_component_idx = gendc_container.get_1st_component_idx_by_typeid(GDC_INTENSITY)
                    if image_component_idx != -1:
                        image_component = gendc_container.get_component_by_index(image_component_idx)
                        part = image_component.get_part_by_index(0)
                        # Access to Comp 0, Part 0's TypeSpecific 3 (where typespecific count start with 1; therefore, index is 2)
                        typespecific3 = part.get_typespecific_by_index(2)
                        # Access to the first 4-byte of typespecific3
                        frame_id = int.from_bytes(typespecific3.to_bytes(8, 'little')[0:4], "little")
                        if required_bit == 8:
                            img_arr = np.frombuffer(part.get_data(), dtype=np.uint8)
                        elif required_bit == 16:
                            img_arr = np.frombuffer(part.get_data(), dtype=np.uint16)

                        if img_arr.size == width * height:
                            if extension == 'raw':
                                img_arr.tofile(os.path.join(output_directory, str(frame_id) + "." + extension))
                            else:
                                img_arr = img_arr * coef
                                img_arr = img_arr.reshape((height, width))
                                if required_bit == 16 and extension != "png":
                                    img_arr = (img_arr / 256).astype("uint8")  # convert to 8 bit
                                if is_color:
                                    img_arr = cv2.cvtColor(img_arr, cv2.COLOR_BayerBG2RGB)  # transfer Bayer to BGR
                                    img_normalized = cv2.normalize(img_arr, None, 0, 1.0,
                                                                   cv2.NORM_MINMAX, dtype=cv2.CV_32F)
                                    (R, G, B) = cv2.split(img_normalized)
                                    R = (R * r_gain).clip(0, 1)
                                    G = (G * g_gain).clip(0, 1)
                                    B = (B * b_gain).clip(0, 1)
                                    img_float32 = cv2.merge([R, G, B])
                                    img_arr = (img_float32 * 255).astype(np.uint8)  # convert to 8 bit 0 ~ 255

                                PILimage = Image.fromarray(img_arr)
                                PILimage.save(os.path.join(output_directory, str(frame_id) + "." + extension))
                        else:
                            log_write("Warning", "Incomplete image-{}".format(str(frame_id)))
                except Exception as e:
                    log_write("ERROR", "convert single frame error: {}".format(e))
                finally:
                    cursor = cursor + payload_in_byte

    def convert_to_video(self,
                         output_directories,
                         is_gendc,
                         to_delete=True,
                         rotate_limit=60,
                         time_out=5):  # time_out is 5 s

        video_writers = []
        payloadsizes = self.dev_info["PayloadSize"]
        num_device = self.dev_info["Number of Devices"]
        pixel_format = self.dev_info["PixelFormat"]
        width = self.dev_info["Width"]
        height = self.dev_info["Height"]
        fps = self.dev_info["FrameRate"]
        '''CONFIGURATION'''
        is_color = False
        if not pixel_format.startswith("Mono"):
            is_color = True
        num_bit_shift = get_num_bit_shift(pixel_format)
        coef = pow(2, num_bit_shift)
        required_bit = required_bit_depth(pixel_format)

        for i in range(num_device):
            output_directory = output_directories[i]
            payload_in_byte = payloadsizes[i]
            try:
                file_list = [f for f in os.listdir(output_directory) if f.endswith(".bin")]  # exclude the json file
                # sort
                if not is_gendc:
                    file_list.sort(
                        key=lambda f: int(f.replace(PREFIX_NAME0, "").replace(PREFIX_NAME1, "").replace('.bin', "")))
                else:
                    file_list.sort(
                        key=lambda f: int(f.replace("gendc_0-", "").replace("gendc_1-", "").replace('.bin', "")))

                if len(file_list) == 0:
                    log_write("WARNING", "No bin file exists")
                    continue
                fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')

                if is_color:
                    out = cv2.VideoWriter(os.path.join(output_directory, "output.mp4".format(i)), fourcc, fps,
                                          (width, height), True)
                else:
                    out = cv2.VideoWriter(os.path.join(output_directory, "output.mp4".format(i)), fourcc, fps,
                                          (width, height), False)
                video_writers.append(out)
                for file in file_list:
                    log_write("INFO", "Converting {} file into mp4, please wait".format(file))
                    file_path = os.path.join(output_directory, file)

                    if not is_gendc:
                        self.convert_single_img_bin_to_video(out,
                                                             file_path,
                                                             required_bit,
                                                             coef,
                                                             is_color, height, width, payload_in_byte, pixel_format,
                                                             rotate_limit)


                    else:
                        self.convert_single_gendc_bin_to_video(out,
                                                               file_path,
                                                               required_bit,
                                                               coef,
                                                               is_color, height, width, payload_in_byte, rotate_limit)

                    if to_delete:
                        del_bin(file_path, time_out)
            except Exception as e:
                log_write("Error", e)
            finally:
                for writer in video_writers:
                    writer.release()
                log_write("DEBUG", "Finish saving video in {}".format(output_directory))

        prefix_name0 = "gendc_0-" if is_gendc else PREFIX_NAME0
        prefix_name1 = "gendc_1-" if is_gendc else PREFIX_NAME1

        for i in range(num_device):
            output_directory = output_directories[i]
            if i == 0:
                sensor_info = read_config(os.path.join(output_directory, prefix_name0 + "config.json"), time_out)
            else:
                sensor_info = read_config(os.path.join(output_directory, prefix_name1 + "config.json"), time_out)
            if len(sensor_info) == 0:
                log_write("WARNING", "Cannot found config file")
                continue
            group_id = sensor_info["group_id"]
            log_write("DEBUG", "Group-id is {}".format(group_id))
            if group_id != 0:
                shutil.move(output_directory, output_directory.replace("group0", "group{}".format(group_id)))

    def convert_single_gendc_bin_to_video(self, video_writer,
                                          file_path,
                                          required_bit,
                                          coef,
                                          is_color, height, width, payload_in_byte, rotate_limit=60):

        cursor = 0
        with open(file_path, mode='rb') as f:
            filecontent = f.read()
            for i in range(rotate_limit):
                if cursor >= len(filecontent):
                    break
                try:
                    gendc_container = gendc.Container(filecontent[cursor:])
                    # get GenDC container information
                    # get first available image component
                    image_component_idx = gendc_container.get_1st_component_idx_by_typeid(GDC_INTENSITY)
                    if image_component_idx != -1:
                        image_component = gendc_container.get_component_by_index(image_component_idx)
                        part = image_component.get_part_by_index(0)
                        # Access to Comp 0, Part 0's TypeSpecific 3 (where typespecific count start with 1; therefore, index is 2)
                        typespecific3 = part.get_typespecific_by_index(2)
                        # Access to the first 4-byte of typespecific3
                        frame_id = int.from_bytes(typespecific3.to_bytes(8, 'little')[0:4], "little")
                        if required_bit == 8:
                            img_arr = np.frombuffer(part.get_data(), dtype=np.uint8)
                        elif required_bit == 16:
                            img_arr = np.frombuffer(part.get_data(), dtype=np.uint16)

                        if img_arr.size == width * height:
                            img_arr = img_arr * coef
                            img_arr = img_arr.reshape((height, width))
                            if is_color:
                                img_arr = cv2.cvtColor(img_arr, cv2.COLOR_BayerBG2RGB)  # transfer Bayer to RGB
                                video_writer.write(img_arr)
                        else:
                            log_write("Warning", "Incomplete image-{}".format(str(frame_id)))
                except Exception as e:
                    log_write("convert single frame error", e)
                finally:
                    cursor = cursor + payload_in_byte

    def convert_single_img_bin_to_video(self, video_writer,
                                        file_path,
                                        required_bit,
                                        coef,
                                        is_color, height, width, payload_in_byte, pixel_format, rotate_limit=60):

        # bin file is in 2D
        img_size = width * height
        position = 0
        with open(file_path, mode='rb') as f:
            if required_bit == 8:
                d = np.fromfile(f, dtype=np.uint8)
            elif required_bit == 16:
                d = np.fromfile(f, dtype=np.uint16)
            else:
                log_write("Error", "PixelFormat: {} is not supported".format(pixel_format))
                return
            file_size_in_byte = len(d) * required_bit // 8
            offset = 0
            slide = 32 // required_bit
            for i in range(rotate_limit):
                if file_size_in_byte < position:
                    break
                f.seek(position)
                frame_id = np.fromfile(f, dtype=np.uint32, count=1)
                position += 4
                offset += slide
                if len(frame_id) > 0:
                    frame_id = frame_id[0]
                else:
                    break
                img_arr = d[offset:offset + img_size]
                offset = offset + img_size
                position = position + payload_in_byte
                if img_arr.size == img_size:
                    img_arr = img_arr * coef
                    img_arr = img_arr.reshape((height, width))
                    if is_color:
                        img_arr = cv2.cvtColor(img_arr, cv2.COLOR_BayerBG2RGB)  # transfer Bayer to RGB
                    video_writer.write(img_arr)
                else:
                    log_write("Warning", "Incomplete frame-{}".format(str(frame_id)))


def del_bin(file_path, time_out):
    try:
        os.remove(file_path)
    except:
        log_write("ERROR", "failed to delete {}".format(file_path))


def read_config(file_path, time_out):
    start = time.time()
    succeed = False
    elapsed = 0
    sensor_info = {}
    while not succeed and elapsed < time_out:
        elapsed = time.time() - start
        try:
            with open(file_path, mode='rb') as f:
                sensor_info = json.load(f)
            succeed = True
        except:
            pass
    if len(sensor_info) == 0:
        log_write("WARNING", "config file is empty")

    return sensor_info


if __name__ == "__main__":
    converter = Converter({"PayloadSize": [640 * 480],
                           "Number of Devices": 1,
                           "PixelFormat": "BayerBG8",
                           "Width": 640,
                           "Height": 480,
                           "FrameRate": 25
                           }, {"Gendc Mode": False})
    converter.convert_to_img(["./output"], False, "jpg", [1, 1], [1, 1], [1, 1])
# convert_to_img(2, ["./output","./output"], 640, 480, extension='jpg', pixel_format="BayerBG8")
