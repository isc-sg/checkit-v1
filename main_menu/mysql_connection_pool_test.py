import mysql.connector
import cython
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import errorcode
from mysql.connector.errors import Error
import multiprocessing as mp
import random
import datetime
from timeit import default_timer as timer

import datetime
import json
import os
import pathlib
import time
import uuid

from sys import exit
import a_eye
import cv2
from skimage.exposure import is_low_contrast
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import errorcode
from mysql.connector.errors import Error
import multiprocessing as mp
from multiprocessing.pool import ThreadPool as Pool
# use ThreadPool instead of Pool due to cython compile error see link below
# https://stackoverflow.com/questions/8804830/python-multiprocessing-picklingerror-cant-pickle-type-function
import subprocess
from wurlitzer import pipes
from passlib.hash import sha512_crypt
import logging
from logging.handlers import RotatingFileHandler
import requests
import configparser
import select_region
from bisect import bisect_left

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

config = configparser.ConfigParser()
config.read('/home/checkit/camera_checker/main_menu/config/config.cfg')
try:
    network_interface = config['DEFAULT']['network_interface']
except configparser.NoOptionError:
    logging.error("Unable to read config file")
    exit(0)

open_file_name = '/tmp/' + str(uuid.uuid4().hex)
close_file_name = '/tmp/' + str(uuid.uuid4().hex)

list_to_process = [[5210, 5211, 5212, 5213, 5214, 5215, 5216, 5217], [5218, 5219, 5220, 5221, 5222, 5223, 5224, 5225], [5226, 5227, 5228, 5229, 5230, 5231, 5232, 5233], [5234, 5235, 5236, 5237, 5238, 5239, 5240, 5241], [5242, 5243, 5244, 5245, 5246, 5247, 5248, 5249], [5250, 5251, 5252, 5253, 5254, 5255, 5256, 5257], [5258, 5259, 5260, 5261, 5262, 5263, 5264, 5265], [5266, 5267, 5268, 5269, 5270, 5271, 5272, 5273], [5274, 5275, 5276, 5277, 5278, 5279, 5280, 5281], [5282, 5283, 5284, 5285, 5286, 5287, 5288, 5289], [5290, 5291, 5292, 5293, 5294, 5295, 5296, 5297], [5298, 5299, 5300, 5301, 5302, 5303, 5304, 5305], [5306, 5307, 5308, 5309, 5310, 5311, 5312, 5313], [5314, 5315, 5316, 5317, 5318, 5319, 5320, 5321], [5322, 5323, 5324, 5325, 5326, 5327, 5328, 5329], [5330, 5331, 5332, 5333, 5334, 5335, 5336, 5337], [5338, 5339, 5340, 5341, 5342, 5343, 5344, 5345], [5346, 5347, 5348, 5349, 5350, 5351, 5352, 5353], [5354, 5355, 5356, 5357, 5358, 5359]]

db_config_checkit = {
    "host": "localhost",
    "user": "checkit",
    "password": "checkit",
    "database": "checkit"
}
checkit_db = mysql.connector.connect(**db_config_checkit)
checkit_cursor = checkit_db.cursor()
checkit_cursor.execute("SELECT * FROM main_menu_camera LIMIT 1")
checkit_result = checkit_cursor.fetchone()

field_names = [i[0] for i in checkit_cursor.description]

camera_id_index = field_names.index('id')
camera_url_index = field_names.index('url')
camera_multicast_address_index = field_names.index('multicast_address')
camera_number_index = field_names.index('camera_number')
camera_name_index = field_names.index('camera_name')
image_regions_index = field_names.index('image_regions')
matching_threshold_index = field_names.index('matching_threshold')
slug_index = field_names.index('slug')

checkit_cursor.execute("SELECT * FROM main_menu_referenceimage LIMIT 1")
checkit_result = checkit_cursor.fetchone()

field_names = [i[0] for i in checkit_cursor.description]
reference_image_id_index = field_names.index('id')
reference_image_url_index = field_names.index('url_id')
reference_image_index = field_names.index('image')
checkit_cursor.close()
checkit_db.close()
print(checkit_result)
def take_closest(my_list, my_number):
    """
    Assumes my_list is sorted. Returns closest value to my_number.

    If two numbers are equally close, return the smallest number.
    """
    pos = bisect_left(my_list, my_number)
    if pos == 0:
        return my_list[0]
    if pos == len(my_list):
        return my_list[-1]
    before = my_list[pos - 1]
    after = my_list[pos]
    if after - my_number < my_number - before:
        return after
    else:
        return before


def create_key(em):
    hash1 = ''
    salt = ''.join(reversed("Checkit"))
    rounds = 656911

    f = open("/etc/machine-id", "r")
    machine_id = f.read()
    machine_id = machine_id.strip("\n")
    shell_output = subprocess.check_output("/bin/df", shell=True)
    l1 = shell_output.decode('utf-8').split("\n")

    for i in l1:
        line = i.split(" ")
        if line[-1] == "/":
            command = "/sbin/blkid | grep " + line[0]
            uuid = ""
            try:
                shell_output = subprocess.check_output(command, shell=True)
            except subprocess.CalledProcessError as error:
                f = open("/etc/fstab", "r")
                fstab_file = f.read()
                fstab_list = fstab_file.split("\n")
                for fstab_line in fstab_list:
                    if fstab_line[0:1] != '#' and fstab_line != '':
                        fstab_line_elements = fstab_line.split()
                        if fstab_line_elements[1] == "/":
                            uuid = fstab_line.split("/dev/disk/by-uuid/")[1].split()[0]
            else:
                l2 = shell_output.decode('utf-8').split(" ")
                uuid = l2[1].strip("UUID=").strip("\"")
            finger_print = uuid + machine_id + em
            hash1 = sha512_crypt.using(rounds=rounds, salt=salt).encrypt(finger_print)

    key = hash1.split("$6$rounds=" + str(rounds) + "$" + salt + "$")
    seg = ''.join(reversed(key[1][11:65]))
    h2 = sha512_crypt.using(rounds=rounds, salt=salt).encrypt(seg)
    pw = h2.split("$6$rounds=" + str(rounds) + "$" + salt + "$")
    return key[1], pw[1]


#license_file = open("/etc/checkit/checkit.lic", "r")
#registered_key = license_file.readline().strip('\n')
#email = license_file.readline().strip('\n')
#license_key, password = create_key(email)
#if license_key != registered_key:
#    logging.error("Licensing error")
#    exit(0)
password = "C203EA1FF06AD85ECED4CC0568ACEF5F"

adm_db = mysql.connector.connect(host="localhost",
                                user="checkit",
                                password="checkit",
                                database="checkit")




def sql_insert(checkit_db, table, fields, values):
    try:
        sql_statement = "INSERT INTO " + table + " " + fields
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement, values)
        checkit_cursor.commit()
        checkit_cursor.close()
    except mysql.connector.Error as e:
        print("Error code:", e.errno)  # error number
        print("SQLSTATE value:", e.sqlstate)  # SQLSTATE value
        print("Error message:", e.msg)  # error message
        print("Error:", e)  # errno, sqlstate, msg values
        s = str(e)
        print("Error:", s)


def sql_select(checkit_db, fields, table, where,  long_sql, fetch_all):
    try:
        if not long_sql:
            sql_statement = "SELECT " + fields + " FROM " + table + " " + where
        else:
            sql_statement = long_sql
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement)
        if fetch_all:
            result = checkit_cursor.fetchall()
        else:
            result = checkit_cursor.fetchone()
        checkit_cursor.close()
        return result
    except mysql.connector.Error as e:
        print("Error code:", e.errno)  # error number
        print("SQLSTATE value:", e.sqlstate)  # SQLSTATE value
        print("Error message:", e.msg)  # error message
        print("Error:", e)  # errno, sqlstate, msg values
        s = str(e)
        print("Error:", s)


def sql_update(checkit_db, table, fields, where):
    sql_statement = "UPDATE " + table + " SET " + fields + where

    try:
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement)
        checkit_cursor.commit()
        checkit_cursor.close()
    except mysql.connector.PoolError as e:
        print("Error code:", e.errno)  # error number
        print("SQLSTATE value:", e.sqlstate)  # SQLSTATE value
        print("Error message:", e.msg)  # error message
        print("Error:", e)  # errno, sqlstate, msg values
        s = str(e)
        print("Error:", s)



def clear_table():
    checkit_cursor = adm_db.cursor()
    sql_statement = "SELECT COUNT(*) FROM connection_test"
    checkit_cursor.execute(sql_statement)
    count = checkit_cursor.fetchone()
    print('Count is', count[0])

    checkit_cursor = adm_db.cursor()
    sql_statement = "DELETE FROM connection_test"
    checkit_cursor.execute(sql_statement)
    adm_db.commit()
    print(checkit_cursor.rowcount, "record(s) deleted")
    adm_db.close()



def open_capture_device(record):
    if record[camera_multicast_address_index]:

        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'add',
                             record[camera_multicast_address_index] + '/32', 'dev', network_interface, 'autojoin'])
        error_output = err.read()
        if error_output:
            logging.error(f"Unable to join multicast group - {error_output}")

        # try all 3 methods for rtsp_transport - this means users don't need to define the transport method
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp_multicast'
        cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)

        if not cap.isOpened():
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
            cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)

        if not cap.isOpened():
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
            cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)

    else:
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
        cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)

    return cap


def close_capture_device(record, cap):
    if record[camera_multicast_address_index]:
        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'del',
                             record[camera_multicast_address_index] + '/32', 'dev', network_interface])
        error_output = err.read()
        if error_output:
            logging.error(f"Unable to leave multicast group - {error_output}")
    cap.release()


def look_for_objects(image):
    url = "http://localhost:8000/api/v1/detection"
    payload = {"model": "yolov4", }
    files = [
        ('image', ('1561-7_26_4.jpg', open('/Users/sam/Downloads/1561-7_26_4.jpg', 'rb'), 'image/jpeg'))
    ]
    headers = {}
    response = requests.request("POST", url, headers=headers, data=payload, files=files)
    objects = ""
    # rtsp://192.168.1.166:7001/e3e9a385-7fe0-3ba5-5482-a86cde7faf48?stream=0
    return objects


def compare_images(base, frame, r, base_color, frame_color):
    # r = ['1', '3', '5', '29', '8', '11', '24', '44', '55', '64']
    h, w = frame.shape[:2]
    all_regions = []
    all_regions.extend(range(1, 65))
    region_scores = {}
    coordinates = select_region.get_coordinates(all_regions, h, w)
    scores = []
    # full_ss = movement(base, frame)
    frame_equalised = cv2.equalizeHist(frame)
    frame_bilateral = cv2.bilateralFilter(frame_equalised, 9, 100, 100)
    base_equalised = cv2.equalizeHist(base)
    base_bilateral = cv2.bilateralFilter(base_equalised, 9, 100, 100)
    full_ss = a_eye.movement(base_bilateral, frame_bilateral)
    count = 0
    for i in coordinates:
        (x, y), (qw, qh) = i
        sub_img_frame = frame_bilateral[y:y + qh, x:x + qw]
        sub_img_base = base_bilateral[y:y + qh, x:x + qw]
        # cv2.imshow("sub of frame", sub_img_frame)
        # cv2.imshow("sub of base", sub_img_base)
        # cv2.waitKey(0)
        ss = 0
        try:
            ss = a_eye.movement(sub_img_base, sub_img_frame)
        except Exception as e:
            logging.error(f"Failed to get movement data {e}")

        # scores.append(ss)
        # print("region", count, "score", round(ss, 2))
        count += 1
        region_scores[count] = round(ss, 2)
    # print("r is ", r)
    # print("Region scores are", region_scores)
    for i in r:
        ss = region_scores[int(i)]
        scores.append(ss)
    # scores_average = mean(scores)

    # print("Scores list is ", scores)
    number_of_regions = len(r)
    # print('number of regions ', number_of_regions)
    scores.sort(reverse=True)
    sum_scores = sum(scores)

    scores_average = sum_scores / number_of_regions
    # print("scores", scores)

    fv = cv2.Laplacian(frame_color, cv2.CV_64F).var()
    # print("Focus Score is %.2f" % fv)
    if scores_average < full_ss:
        full_ss = scores_average
    full_ss = round(full_ss, 2)
    scores_average = round(scores_average, 2)
    fv = round(fv, 2)

    if is_low_contrast(frame, 0.25):
        print("Log image is of poor quality")
        full_ss = 0
    if is_low_contrast(base, 0.25):
        print("Base image is of poor quality")
        full_ss = 0

    logging.debug(f"Match Score for full image is {full_ss}")
    logging.debug(f"Match Score for regions is {scores_average}")
    logging.debug(f"Focus value is {fv}")
    logging.debug(f"All region scores are {region_scores}")

    return full_ss, fv, region_scores


def no_base_image(checkit_db, record):
    # connection = connection_pool.get_connection()
    # checkit_cursor = connection.cursor()
    logging.debug(f"No base image for {record}")
    capture_device = open_capture_device(record)

    if not capture_device.isOpened():
        logging.error(f"unable to open capture device {record[camera_url_index]}")
        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
        table = "main_menu_logimage"
        fields = "(url_id, image, matching_score, region_scores, current_matching_threshold, " \
                 "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
        values = (str(record[camera_id_index]), "", "0", "0", "0", "0", "Capture Error", now)
        sql_insert(checkit_db, table, fields, values)
        close_capture_device(record, capture_device)
        return
    else:
        try:
            able_to_read, frame = capture_device.read()
            if not able_to_read:
                raise NameError()
        except cv2.error as e:
            logging.error(f"cv2 error {e}")
        except NameError:
            logging.error(f"Unable to read camera {record[camera_number_index]} - {record[camera_name_index]}")
        else:
            logging.debug(f"Able to capture base image on {record[camera_name_index]}")
            time_stamp = datetime.datetime.now()
            file_name = "/home/checkit/camera_checker/media/base_images/" + str(record[camera_id_index]) + "/" + \
                        time_stamp.strftime('%H') + ".jpg"
            directory = "/home/checkit/camera_checker/media/base_images/" + str(record[camera_id_index])
            try:
                pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                if not os.path.isfile(file_name):
                    cv2.imwrite(file_name, frame)
                    sql_file_name = file_name.strip("/home/checkit/camera_checker/media/")
                    table = "main_menu_referenceimage"
                    fields = "(url_id, image, hour) VALUES (%s,%s,%s)"
                    values = (str(record[camera_id_index]), sql_file_name, time_stamp.strftime('%H'))
                    sql_insert(checkit_db, table, fields, values)
            except OSError as error:
                logging.error(f"Unable to create base image directory/file {error}")


def increment_transaction_count(checkit_db):
    connected = False
    while not connected:
        try:
            checkit_cursor = checkit_db.cursor()
            sql = "UPDATE main_menu_licensing SET transaction_count =  transaction_count + 1 WHERE id = 1"
            checkit_cursor.execute(sql)
            checkit_cursor.commit()
            checkit_cursor.close()
            connected = True
        except mysql.connector.Error as e:
            logging.error(f"Database connection error at 488 {e}")
            connected = False

    connected = False
    while not connected:
        try:
            admin_cursor = adm_db.cursor()
            sql = "UPDATE adm SET tx_count =  tx_count + 1 WHERE id = 1"
            admin_cursor.execute(sql)
            admin_cursor.commit()
            admin_cursor.close()

            connected = True
        except mysql.connector.Error as e:
            logging.error(f"Database connection error at 503 {e}")
            connected = False


def process_list(x):
    db_config_checkit = {
        "host": "localhost",
        "user": "checkit",
        "password": "checkit",
        "database": "checkit"
    }
    checkit_db = mysql.connector.connect(**db_config_checkit)
    checkit_cursor = checkit_db.cursor()
    checkit_cursor.execute("SELECT * FROM main_menu_camera LIMIT 1")
    checkit_result = checkit_cursor.fetchone()

    field_names = [i[0] for i in checkit_cursor.description]

    camera_id_index = field_names.index('id')
    camera_url_index = field_names.index('url')
    camera_multicast_address_index = field_names.index('multicast_address')
    camera_number_index = field_names.index('camera_number')
    camera_name_index = field_names.index('camera_name')
    image_regions_index = field_names.index('image_regions')
    matching_threshold_index = field_names.index('matching_threshold')
    slug_index = field_names.index('slug')

    checkit_cursor.execute("SELECT * FROM main_menu_referenceimage LIMIT 1")
    checkit_result = checkit_cursor.fetchone()

    field_names = [i[0] for i in checkit_cursor.description]
    reference_image_id_index = field_names.index('id')
    reference_image_url_index = field_names.index('url_id')
    reference_image_index = field_names.index('image')
    checkit_cursor.close()

    for camera in x:
        fields = "*"
        table = "main_menu_camera"
        where = "WHERE id = " + "\"" + str(camera) + "\""
        long_sql = None
        current_record = sql_select(checkit_db, fields, table, where, long_sql, fetch_all=False)
        regions = current_record[image_regions_index]

        if regions == '0' or regions == "[]":
            regions = []
            regions.extend(range(1, 65))
        else:
            regions = eval(regions)

        current_time = datetime.datetime.now()
        hour = current_time.strftime('%H')
        fields = "hour"
        table = "main_menu_referenceimage"
        where = "WHERE url_id = " + "\"" + str(current_record[camera_id_index]) + "\""
        long_sql = None
        hours = sql_select(checkit_db, fields, table, where, long_sql, fetch_all=True)
        int_hours = []

        if hours:
            for i in range(0, len(hours)):
                int_hours.append(hours[i][0])
                int_hours[i] = int(int_hours[i])
            hour = int(hour)
            if hour not in int_hours:
                no_base_image(current_record)
            else:
                closest_hour = take_closest(int_hours, hour)
                closest_hour = str(closest_hour).zfill(2)
                fields = "image"
                table = "main_menu_referenceimage"
                where = "WHERE url_id = " + "\"" + str(current_record[camera_id_index]) +\
                        "\"" + " AND hour = " + "\"" + closest_hour + "\""
                long_sql = None
                image = sql_select(checkit_db, fields, table, where, long_sql, fetch_all=False)
                image = image[0]

                base_image = "/home/checkit/camera_checker/media/" + image
                if not os.path.isfile(base_image):
                    logging.error(f'Base image missing for {base_image}')
                    return

                capture_device = open_capture_device(current_record)

                able_to_read = False

                if capture_device.isOpened():
                    able_to_read, image_frame = capture_device.read()
                    close_capture_device(current_record, capture_device)
                else:
                    logging.error(f"Unable to open capture device {current_record[camera_url_index]}")
                if able_to_read:
                    image_base = cv2.imread(base_image)
                    if image_base is None:
                        logging.error(f"Base image is logged but unable to file {base_image}")
                        exit()
                    time_stamp = datetime.datetime.now()
                    time_stamp_string = datetime.datetime.strftime(time_stamp, "%Y-%m-%d %H:%M:%S.%f")
                    directory = "/home/checkit/camera_checker/media/logs/" + str(time_stamp.year) + "/" + \
                                str(time_stamp.month) + "/" + str(time_stamp.day)
                    log_image_file_name = directory + "/" + str(current_record[camera_id_index]) + \
                                          "-" + str(time_stamp.hour) + ":" + str(time_stamp.minute) + ":" + \
                                          str(time_stamp.second) + ".jpg"

                    try:
                        pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                    except OSError as error:
                        logging.error(f"Error saving log file {error}")

                    able_to_write = cv2.imwrite(log_image_file_name, image_frame)
                    capture_dimensions = image_frame.shape[:2]
                    reference_dimensions = ()
                    status = "failed"

                    if not able_to_write:
                        logging.error(f"Unable to write log image {log_image_file_name}")

                    # write the log file - create variable to store in DB
                    else:
                        try:
                            image_base_grey = cv2.cvtColor(image_base, cv2.COLOR_BGR2GRAY)
                            image_frame_grey = cv2.cvtColor(image_frame, cv2.COLOR_BGR2GRAY)
                            reference_dimensions = image_base_grey.shape[:2]
                            capture_dimensions = image_frame_grey.shape[:2]
                            status = "success"
                        except cv2.error as err:
                            logging.error(f"Error in converting image {err}")
                            status = "failed"
                            # need to test this return with cv2 error
                            return

                        if reference_dimensions != capture_dimensions or status == "failed":
                            logging.error(f"Image sizes don't match on camera number {current_record[camera_number_index]}")
                            now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
                            sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                            table = "main_menu_logimage"
                            fields = "(url_id, image, matching_score, region_scores, current_matching_threshold, " \
                                     "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                            values = (str(current_record[camera_id_index]), sql_file_name,
                                      "0", "{}", "0", "0", "Image Size Error", now)
                            sql_insert(checkit_db, table, fields, values)

                            increment_transaction_count(checkit_db)
                        else:
                            matching_score, focus_value, region_scores = compare_images(image_base_grey,
                                                                                        image_frame_grey,
                                                                                        regions, image_base,
                                                                                        image_frame)
                            sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                            if matching_score < current_record[matching_threshold_index]:
                                action = "Failed"
                            else:
                                action = "Pass"

                            table = "main_menu_logimage"
                            fields = "(url_id, image, matching_score, region_scores, " \
                                                    "current_matching_threshold, " \
                                                    "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                            values = (str(current_record[camera_id_index]), sql_file_name, float(matching_score),
                                      json.dumps(region_scores),
                                      float(current_record[matching_threshold_index]), float(focus_value),
                                      action, time_stamp_string)
                            sql_insert(checkit_db, table, fields, values)

                            table = "main_menu_camera"
                            fields = "last_check_date = " + "\"" + time_stamp_string + "\""
                            where = " WHERE id = " + "\"" + str(current_record[camera_id_index]) + "\""
                            sql_update(checkit_db, table, fields, where)

                            increment_transaction_count(checkit_db)
                else:
                    # print("unable to read")
                    now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")

                    table = "main_menu_logimage"
                    fields = "(url_id, image, matching_score, region_scores, " \
                             "current_matching_threshold, focus_value, action, creation_date) " \
                             "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                    values = (str(current_record[camera_id_index]), "", "0", "{}", "0", "0", "Capture Error", now)
                    sql_insert(checkit_db, table, fields, values)
                    increment_transaction_count(checkit_db)
        else:
            # only gets here with new camera
            logging.info(f"No base image for camera number {current_record[camera_number_index]} - "
                         f"{current_record[camera_name_index]}")
            no_base_image(current_record)
            increment_transaction_count(checkit_db)
    adm_db.close()

# list_of_numbers = [*range(0, 100000)]
mp.set_start_method("fork")

# clear_table()

start = timer()
print('Starting 16 thread run')
with mp.Pool(8) as p:
    p.map(process_list, list_to_process)
    p.close()
    p.join()

end = timer()
print("Time for 16 run", end-start)
