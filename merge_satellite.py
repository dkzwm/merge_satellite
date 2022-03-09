# coding=utf-8
import math
import os
from osgeo import gdal
import numpy.matlib as matlib
import sys, getopt
import psutil

IMAGE_EXTENSION = ".png"


def num2deg(x_tile, y_tile, zoom):
    n = 2.0**zoom
    lng_deg = x_tile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y_tile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lng_deg


def num2deg(x_pixel, y_pixel, x_tile, y_tile, zoom):
    x_pixel_of_tile = x_pixel / 256.0
    y_pixel_of_tile = y_pixel / 256.0
    lng = (x_tile + x_pixel_of_tile) / math.pow(2, zoom) * 360 - 180
    lat = math.atan(
        math.sinh(math.pi * (
            1 - 2 *
            (y_tile + y_pixel_of_tile) / math.pow(2, zoom)))) * 180.0 / math.pi
    return lat, lng


def deg2num(lat_deg, lng_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0**zoom
    x_tile = int((lng_deg + 180.0) / 360.0 * n)
    y_tile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x_tile, y_tile


def compress(path, target_path, compress_method="LZW", jpeg_quality=100):
    src_ds = gdal.Open(path)
    driver = gdal.GetDriverByName('GTiff')
    opts = ["TILED=YES", "COMPRESS={0}".format(compress_method)]
    if compress_method == "JPEG":
        opts.append("JPEG_QUALITY={0}".format(jpeg_quality))
    elif compress_method == "LZMA" or compress_method == "DEFLATE ":
        opts.append("NUM_THREADS={0}".format(psutil.cpu_count()))
    dst_ds = driver.CreateCopy(target_path, src_ds, strict=1, options=opts)
    src_ds = None
    dst_ds = None
    del dst_ds
    del src_ds


def merge(input_dir, output_dir, zoom, min_x, max_x, min_y, max_y, req_trans,
          do_compress, compress_method, jpeg_quality):
    size = 256
    x = y = 0
    output_name = output_dir + os.sep + "output.tif"
    compressed_name = output_dir + os.sep + "compressed.tif"
    n_w = num2deg(1, 1, min_x, min_y, zoom)
    s_e = num2deg(256, 256, max_x, max_y, zoom)
    print(('North-West tile (x,y):', (min_x, min_y).__str__()))
    print(('North-West coordinate (lat,lng):', n_w))
    print(('South-East tile (x,y):', (max_x, max_y).__str__()))
    print(('South-East coordinate (lat,lng):', s_e))
    print(('Rows:', max_x - min_x))
    print(('Columns:', max_y - min_y))
    print(('Output image size:', str(size * (max_y - min_y)), '*',
           str(size * (max_x - min_x))))
    tif_width = size * (max_x - min_x + 1)
    tif_height = size * (max_y - min_y + 1)
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(output_name, tif_width, tif_height,
                           4 if req_trans == 1 else 3, gdal.GDT_Byte)
    out_ds.SetProjection(
        """GEOGCS["WGS 84", DATUM["WGS_1984", SPHEROID["WGS 84", 6378137, 298.257223563, AUTHORITY["EPSG", "7030"]], AUTHORITY["EPSG", "6326"]], PRIMEM["Greenwich", 0, AUTHORITY["EPSG", "8901"]], UNIT["degree", 0.01745329251994328, AUTHORITY["EPSG", "9122"]], AUTHORITY["EPSG", "4326"]]"""
    )
    out_ds.SetGeoTransform([
        n_w[1], (s_e[1] - n_w[1]) / tif_width, 0, n_w[0], 0,
        -(n_w[0] - s_e[0]) / tif_height
    ])
    i = 0
    out_ds_rb1 = out_ds.GetRasterBand(1)
    out_ds_rb2 = out_ds.GetRasterBand(2)
    out_ds_rb3 = out_ds.GetRasterBand(3)
    out_ds_rb4 = out_ds.GetRasterBand(4) if req_trans == 1 else None
    no_transparent = matlib.repmat(255, 256, 256)
    count = (max_x - min_x + 1) * (max_y - min_y + 1)
    for x in range(min_x, max_x + 1):
        print("Process dir:%s" % (input_dir + os.sep + str(x)))
        for y in range(min_y, max_y + 1):
            i += 1
            tmp_name = input_dir + os.sep + str(x) + os.sep + str(
                y) + IMAGE_EXTENSION
            if os.path.exists(tmp_name):
                in_ds = gdal.Open(tmp_name)
                if in_ds is not None:
                    data = in_ds.GetRasterBand(1).ReadAsArray()
                    out_ds_rb1.WriteArray(data, (x - min_x) * size,
                                          (y - min_y) * size)
                    data = in_ds.GetRasterBand(2).ReadAsArray()
                    out_ds_rb2.WriteArray(data, (x - min_x) * size,
                                          (y - min_y) * size)
                    data = in_ds.GetRasterBand(3).ReadAsArray()
                    out_ds_rb3.WriteArray(data, (x - min_x) * size,
                                          (y - min_y) * size)
                    if req_trans == 1:
                        out_ds_rb4.WriteArray(no_transparent,
                                              (x - min_x) * size,
                                              (y - min_y) * size)
            print('%s%% ' % round((i * 1.0 / count) * 100, 2))
    out_ds = None
    del out_ds
    if do_compress:
        print("Start compress")
        print("------------------------")
        compress(output_name, compressed_name, compress_method, jpeg_quality)
        print("------------------------")
    print("Output files info:")
    print("------------------------")
    print(output_name)
    if do_compress: print(compressed_name)
    print("------------------------")


def calcUseDir(dir, req_trans):
    print('Calculating used by dir.')
    print("------------------------")
    #The directory structure is like this "0" + os.sep + "0" + os.sep + "0.png"
    zoom = min_x = max_x = min_y = max_y = -1
    i = 0
    for parent, _, names in os.walk(dir):
        for filename in names:
            if filename.endswith(IMAGE_EXTENSION):
                i += 1
                split_str = parent.split(os.sep)
                x = int(split_str[-1])
                y = int(filename[:-IMAGE_EXTENSION.__len__()])
                if zoom == -1:
                    zoom = int(split_str[-2])
                    min_x = max_x = x
                    min_y = max_y = y
                else:
                    max_x = max(max_x, x)
                    min_x = min(min_x, x)
                    max_y = max(max_y, y)
                    min_y = min(min_y, y)
    if req_trans == -1:
        req_trans = 1 if (max_x - min_x + 1) * (max_y - min_y + 1) != i else 0
    print("------------------------")
    return zoom, min_x, max_x, min_y, max_y, req_trans


def calcUseBounds(input_dir, zoom, bounds, req_trans):
    print('Calculating used by bounds.')
    print("------------------------")
    n_w = deg2num(bounds[0], bounds[1], zoom)
    s_e = deg2num(bounds[2], bounds[3], zoom)
    min_x = n_w[0]
    max_x = s_e[0] - 1
    min_y = n_w[1]
    max_y = s_e[1] - 1
    i = 0
    if req_trans == -1:
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                tmp_name = input_dir + os.sep + str(x) + os.sep + str(
                    y) + IMAGE_EXTENSION
                if os.path.exists(tmp_name):
                    i += 1
        req_trans = 1 if (max_x - min_x + 1) * (max_y - min_y + 1) != i else 0
    print("------------------------")
    return zoom, min_x, max_x, min_y, max_y, req_trans


def str2bool(s):
    return s.lower() in ['true', '1', 't', 'y', 'yes', "do", "ok"]


def main(argv):
    input_dir = ''
    output_dir = ''
    bounds = []
    zoom = -1
    req_trans = -1
    do_compress = True
    compress_method = "JPEG"
    jpeg_quality = 100
    try:
        opts, _ = getopt.getopt(argv, "hi:o:b:t:z:d:c:q:", [
            "input_dir=", "output_dir=", "bounds=", "trans_cl_req=", "zoom=",
            "do_compress=", "compress=", "quality="
        ])
    except getopt.GetoptError:
        print(
            'merge_satellite.py -i <input dir> -o <output dir> -b <latitude longitude bounds(-85.00,180.00,85.00,-180.00)> -t <transparent channel required(true/false)> -z <zoom level> -d <compress tif required(true/false)>-c <compress method> -q <JPEG compress quality>\n'
        )
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print(
                'merge_satellite.py -i <input dir> -o <output dir> -b <latitude longitude bounds(-85.00,180.00,85.00,-180.00)> -t <transparent channel required(true/false)> -z <zoom level -d <compress tif required(true/false)> -c <compress method> -q <JPEG compress quality>>\n'
            )
            print(
                'merge_satellite.py --input_dir=<input dir> --output_dir=<output dir> --bounds=<latitude longitude bounds(-85.00,180.00,85.00,-180.00)> --trans_cl_req=<transparent channel required(true/false)> --zoom=<zoom level> -do_compress=<compress tif required(true/false)> --compress=<compress method(LZW,JPEG)> --quality=<JPEG compress quality>\n'
            )
            sys.exit()
        elif opt in ("-i", "--input_dir"):
            input_dir = arg
            if input_dir.endswith(os.sep) or not (os.path.exists(input_dir)):
                print('Please enter the correct input file directory')
                sys.exit(2)
        elif opt in ("-o", "--output_dir"):
            output_dir = arg
            if output_dir.endswith(os.sep) or not (os.path.exists(output_dir)):
                print('Please enter the correct output file directory')
                sys.exit(2)
        elif opt in ("-t", "--trans_cl_req"):
            req_trans = 1 if str2bool(arg) else 0
        elif opt in ("-b", "--bounds"):
            bound_str = arg
            latlng_arr = bound_str.split(',')
            if latlng_arr.__len__() != 4:
                print('Please enter the correct latitude and longitude range')
                sys.exit(2)
            bounds.append(float(latlng_arr[0]))
            bounds.append(float(latlng_arr[1]))
            bounds.append(float(latlng_arr[2]))
            bounds.append(float(latlng_arr[3]))
        elif opt in ("-z", "--zoom"):
            zoom = int(arg)
        elif opt in ("-d", "--do_compress"):
            do_compress = str2bool(arg)
        elif opt in ("-c", "--compress"):
            compress_methods = [
                "LZW", "JPEG", "PACKBITS", "DEFLATE", "CCITTRLE", "CCITTFAX3",
                "CCITTFAX4", "LZMA", "ZSTD", "LERC", "LERC_DEFLATE",
                "LERC_ZSTD", "WEBP"
            ]
            if arg not in compress_methods:
                print(
                    'Please enter the correct value:{} cannot enter value {}. The value must be in {}'
                    .format(opt, arg, compress_methods))
                sys.exit(2)
            compress_method = arg
        elif opt in ("-quality", "--quality"):
            jpeg_quality = int(arg)

    if input_dir == None or input_dir == "":
        print('The input file directory is required')
        sys.exit(2)
    if output_dir == None or output_dir == "":
        print('The output file directory is required')
        sys.exit(2)
    if bounds.__len__() != 0 and zoom == -1:
        print(
            'When passing the latitude and longitude range, the zoom level is required'
        )
        sys.exit(2)
    if bounds.__len__() == 0:
        merge(input_dir, output_dir, *calcUseDir(input_dir, req_trans),
              do_compress, compress_method, jpeg_quality)
    else:
        merge(input_dir, output_dir,
              *calcUseBounds(input_dir, zoom, bounds, req_trans), do_compress,
              compress_method, jpeg_quality)


if __name__ == "__main__":
    main(sys.argv[1:])