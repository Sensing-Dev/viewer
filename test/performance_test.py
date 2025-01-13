import argparse
import os

from PIL import Image
import numpy as np
from gendc_python.genicam import tool as genicam

import re
import struct
import json

GDC_INTENSITY = 0x0000000000000001
Mono8 = genicam.pfnc_convert_pixelformat("Mono8")
Mono10 = genicam.pfnc_convert_pixelformat("Mono10")
Mono12 = genicam.pfnc_convert_pixelformat("Mono12")
RGB8 =genicam.pfnc_convert_pixelformat("RGB8")
BGR8 = genicam.pfnc_convert_pixelformat("BGR8")
BayerBG8 = genicam.pfnc_convert_pixelformat("BayerBG8")
BayerBG10 = genicam.pfnc_convert_pixelformat("BayerBG10")
BayerBG12 = genicam.pfnc_convert_pixelformat("BayerBG12")

image_ext = ['bin', 'png', 'jpg', 'jpeg', 'png', 'bmp', 'raw']


def get_config_info(config_file_path):
    with open(config_file_path, mode='r') as f:
        config = json.loads(f.read())
        w = config["width"]
        h = config["height"]
        d = 2 if config["pfnc_pixelformat"] == Mono10 or config["pfnc_pixelformat"] == Mono12 \
            else 1
        c = 3 if config["pfnc_pixelformat"] == RGB8 or config["pfnc_pixelformat"] == BGR8 \
            else 1
    return w, h, d, c


def frame_check_bin(camera_dir, ext_items, ext='bin', blackpixel=False):
    print('-{}({})'.format(camera_dir, ext))
    ext_items = sorted(ext_items, key=lambda s: int(re.search(r'-(\d+)\.bin', s).group(1)))

    config_list = [f for f in os.listdir(camera_dir) if f.endswith('config.json')]
    if not len(config_list) == 1:
        raise Exception('Multiple config files found')
    w, h, d, c = get_config_info(os.path.join(camera_dir, config_list[0]))
    framesize = w * h * d * c
    expected_idx = 0
    offset_idx = 0
    num_dropped_frame = 0
    num_catch = 0

    for bin_idx, bf in enumerate(ext_items):
        bin_file = os.path.join(camera_dir, bf)

        with open(bin_file, mode='rb') as ifs:
            filecontent = ifs.read()
            cursor = 0
            first_frame = True

            while cursor < len(filecontent):
                try:
                    # TODO return NULL for non-gendc format
                    gendc_container = gendc.Container(filecontent[cursor:])
                    image_component_idx = gendc_container.get_1st_component_idx_by_typeid(GDC_INTENSITY)
                    image_component = gendc_container.get_component_by_index(image_component_idx)
                    part = image_component.get_part_by_index(0)
                    typespecific3 = part.get_typespecific_by_index(2)
                    saved_idx = int.from_bytes(typespecific3.to_bytes(8, 'little')[0:4], "little")
                    cursor = cursor + gendc_container.get_container_size()

                except:
                    saved_idx = struct.unpack('I', filecontent[cursor:cursor + 4])[0]
                    cursor = cursor + 4 + framesize

                if first_frame and bin_idx == 0:
                    expected_idx = saved_idx
                    offset_idx = saved_idx
                    first_frame = False

                while expected_idx != saved_idx:
                    expected_idx += 1
                    num_dropped_frame += 1

                expected_idx += 1
                num_catch += 1

    return num_dropped_frame, num_catch, [offset_idx, expected_idx - 1], None


def frame_check_non_bin(camera_dir, ext_items, ext, blackpixel=False):
    print('-{}({})'.format(camera_dir, ext))
    ext_items = sorted(ext_items)
    # print(categorized_items[ext])
    expected_idx = ext_items[0]
    num_dropped_frame = 0
    num_catch = 0
    num_dark = {'25': 0, '50': 0, '75': 0, '100': 0}
    for saved_idx in ext_items:
        while expected_idx != saved_idx:
            # print('expected: {}, actual: {}'.format(expected_idx, saved_idx))
            expected_idx += 1
            num_dropped_frame += 1
        expected_idx += 1
        num_catch += 1

        img_file_name = os.path.join(camera_dir, str(saved_idx) + '.' + ext)
        if not os.path.isfile(img_file_name):
            raise Exception('Image {} does not exist'.format(img_file_name))
        if blackpixel:
            img = Image.open(img_file_name)
            numpydata = np.array(img)
            img_size = numpydata.size
            num_black = np.sum(numpydata == 0)
            black_ratio = num_black * 100.00 / img_size
            if black_ratio >= 25.0:
                num_dark['25'] += 1
            if black_ratio >= 50.0:
                num_dark['50'] += 1
            if black_ratio >= 75.0:
                num_dark['75'] += 1
            if black_ratio > 99.9:
                num_dark['100'] += 1

    return num_dropped_frame, num_catch, [ext_items[0], ext_items[-1]], num_dark


def get_ext_items(all_items_in_dir, ext):
    if ext == 'bin':
        return [f for f in all_items_in_dir if f.endswith(".bin")]
    else:
        return [int(f.split('.')[0]) for f in all_items_in_dir if f.endswith(ext)]


def main():
    parser = argparse.ArgumentParser(description="Check frame catch rate")
    parser.add_argument('-d', '--directory', type=str,
                        help='Directory that has saved files', required=True)
    parser.add_argument('-b', '--blackpixel', action='store_true',
                        help='Check if image is mostly black')
    parser.add_argument('-g', '--groupid', type=str, default='group0',
                        help='Directory that has saved files')

    directory_name = parser.parse_args().directory
    blackpixel = parser.parse_args().blackpixel
    groupid = parser.parse_args().groupid

    if not (os.path.exists(directory_name) and os.path.isdir(directory_name)):
        raise Exception("Directory " + directory_name + " does not exist")

    groupid_dir = os.path.join(directory_name, groupid)
    if not (os.path.exists(groupid_dir) and os.path.isdir(groupid_dir)):
        raise Exception("Directory " + groupid_dir + " does not exist")

    camera_dir_names = [d for d in os.listdir(groupid_dir) if d.startswith('camera')]

    for camera_dir_name in camera_dir_names:
        camera_dir = os.path.join(groupid_dir, camera_dir_name)
        if not os.path.isdir(camera_dir):
            raise Exception("Directory " + camera_dir + " does not exist")

        all_items_in_dir = os.listdir(camera_dir)
        categorized_items = {}

        for ext in image_ext:

            categorized_items[ext] = get_ext_items(all_items_in_dir, ext)
            if len(categorized_items[ext]) > 0:

                if ext == 'bin':
                    num_dropped_frame, num_catch, [min_idx, max_idx], num_dark = frame_check_bin(camera_dir,
                                                                                                 categorized_items[ext])
                else:
                    num_dropped_frame, num_catch, [min_idx, max_idx], num_dark = frame_check_non_bin(camera_dir,
                                                                                                     categorized_items[
                                                                                                         ext], ext,
                                                                                                     blackpixel)

                num_total = max_idx - min_idx + 1
                stats = (num_total - num_dropped_frame) * 100.0 / num_total
                print('  frame catch rate     : {}%'.format(stats))
                print('  frame catch          : {} frames'.format(num_catch))
                print('  num frames           : {}'.format(num_total))
                print('  frames               : {} - {}'.format(min_idx, max_idx))
                if blackpixel and num_dark:
                    print('  black pixels > 25%   : {}'.format(num_dark['25']))
                    print('  black pixels > 50%   : {}'.format(num_dark['50']))
                    print('  black pixels > 75%   : {}'.format(num_dark['75']))
                    print('  black pixels > 99.9% : {}'.format(num_dark['100']))


if __name__ == "__main__":
    main()
