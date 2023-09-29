# from pathos.multiprocessing import ProcessingPool as Pool
from pathos.multiprocessing import ProcessingPool, cpu_count
import cython
import pathos
import math
import numpy as np
import uuid
import mysql.connector
import datetime
import json
import os
import pathlib
from sys import exit
import a_eye
import cv2
from skimage.exposure import is_low_contrast
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import errorcode
import subprocess
from wurlitzer import pipes
from passlib.hash import sha512_crypt
import logging
from logging.handlers import RotatingFileHandler
import requests
import configparser
import select_region
from bisect import bisect_left
import hashlib
import itertools
import socket
import get_sdp

# open_file_name = '/tmp/' + str(uuid.uuid4().hex)
# close_file_name = '/tmp/' + str(uuid.uuid4().hex)


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

config = configparser.ConfigParser()
config.read('/home/checkit/camera_checker/main_menu/config/config.cfg')

try:
    if config.has_option('DEFAULT', 'log_alarms'):
        try:
            log_alarms = config.getboolean('DEFAULT', 'log_alarms')
        except ValueError:
            log_alarms = False
    else:
        log_alarms = False
    network_interface = config['DEFAULT']['network_interface']
    HOST = None
    if config.has_option('DEFAULT', 'synergy_host', ):
        try:
            HOST = config.get('DEFAULT', 'synergy_host', fallback=None)
        except ValueError:
            logging.error("Please check config file for synergy host address")

    PORT = 0
    if config.has_option('DEFAULT', 'synergy_port',):
        try:
            PORT = config.getint('DEFAULT', 'synergy_port', fallback=0)
        except ValueError:
            logging.error("Please check config file for synergy port number")

    CHECKIT_HOST = config['DEFAULT']['checkit_host']
except configparser.NoOptionError:
    logging.error("Unable to read config file")
    exit(0)


cpus = cpu_count()


def take_closest(my_list, my_number):
    """
    Assumes my_list is sorted. Returns the closest value to my_number.

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


def get_transparent_edge(input_image, color):
    edge_image = cv2.Canny(input_image, 100, 200)
    edge_image = cv2.cvtColor(edge_image, cv2.COLOR_RGB2BGR)
    edge_image[np.where((edge_image == [255, 255, 255]).all(axis=2))] = color
    gray_image = cv2.cvtColor(edge_image, cv2.COLOR_BGR2GRAY)
    _, alpha = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY)
    b, g, r = cv2.split(edge_image)
    rgba_image = [b, g, r, alpha]
    final_image = cv2.merge(rgba_image, 4)
    return final_image


def send_alarms(list_of_cameras):
    if not log_alarms:
        return
    if HOST is None or PORT == 0:
        logging.error(f"Error in config - HOST = {HOST}, PORT = {PORT}")

        return
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((HOST, PORT))
    except socket.error as e:
        logging.error(f"Error sending to alarm server - {e}")
        return
    finally:
        s.close()
    checkit_db = mysql.connector.connect(
                    host="localhost",
                    user="checkit",
                    password="checkit",
                    database="checkit"
            )
    cursor = checkit_db.cursor()
    # sql_statement = "SELECT url_id FROM main_menu_logimage WHERE action != 'Pass' AND url_id IN (201,200,199) AND creation_date >= '2023-04-17 12:48:24.035230'"
    sql_statement = "select state_timestamp  from main_menu_enginestate where state = 'STARTED'  ORDER BY id DESC LIMIT 1"
    cursor.execute(sql_statement)
    timestamp = cursor.fetchone()[0]
    timestamp = datetime.datetime.strftime(timestamp, "%Y-%m-%d %H:%M:%S")
    # print(timestamp)
    combined_list = list(itertools.chain.from_iterable(list_of_cameras))
    sql_statement = "SELECT url_id, creation_date, action, image, matching_score, focus_value, light_level " \
                    "FROM main_menu_logimage " \
                    "WHERE action != 'Pass' AND url_id IN ({}) " \
                    "AND creation_date >= '{}'".format(','.join(map(str, combined_list)), timestamp)
    cursor = checkit_db.cursor()
    cursor.execute(sql_statement)
    f = cursor.fetchall()
    # print(len(f))
    for i in f:
        url_id = i[0]
        creation_date = datetime.datetime.strftime(i[1], "%Y-%m-%d %H:%M:%S")
        action = i[2]
        log_image: str = i[3]
        matching_score = i[4]
        focus_value = i[5]
        light_level = i[6]
        sql_statement = "SELECT * FROM main_menu_camera WHERE id = {}".format(url_id)
        cursor.execute(sql_statement)
        camera_details = cursor.fetchone()
        # print(camera_details)
        camera_url = camera_details[1]
        camera_number = camera_details[3]
        camera_name = camera_details[4]
        camera_location = camera_details[6]
        image = "http://" + CHECKIT_HOST + "/media/" + log_image
        # log_image = cv2.imread("/home/checkit/camera_checker/media/" + log_image)
        # base_image = cv2.imread("/home/checkit/camera_checker/media/" + "base_images/" \
        #              + str(url_id) + "/" + log_image.split("-")[1].split(":")[0].zfill(2) + ".jpg")
        # log_transparent_edges = get_transparent_edge(log_image, [0, 0, 255])
        # log_transparent_edges = log_transparent_edges[:, :, :3]
        # merged_image = cv2.addWeighted(log_transparent_edges, 1, base_image, 1, 0)
        # cv2.imwrite("/tmp/.tmp_image.jpg", merged_image)

        # cv2.imshow("log", image)
        # cv2.waitKey(0)
        # print(url_id, camera_number, camera_name, camera_url, camera_location,
        #       creation_date, action, log_image, matching_score, focus_value, light_level)
        message = "Error detected on camera " + camera_url \
                  + "|with matching score result " + str(matching_score) \
                  + "|at location " + camera_location
        send_alarm = """<?xml version="1.0" encoding="UTF-8"?><Request command="sendAlarm" id="123">""" \
                     + "<message>" + "Checkit Alarm" + "</message> " \
                     + "<text>" + message + "</text>" \
                     + "<camera>" + camera_name + "</camera>" \
                     + "<param1>" + camera_location + "</param1>" \
                     + "<param2>" + str(camera_number) + "</param2>" \
                     + "<param3>" + str(camera_url) + "</param3>" \
                     + "<alarmType>" + "Checkit Alarm" + "</alarmType> " \
                     + "<delimiter>|</delimiter><sourceId>2600</sourceId>" \
                     + "<jpeg>" + image + "</jpeg>" \
                     + "<autoClose>true</autoClose></Request>""" + "\x00"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((HOST, PORT))
            s.send(send_alarm.encode())
            reply = s.recv(8192).decode().rstrip("\x00")
        except socket.error as e:
            logging.error(f"Error sending to alarm server - {e}")
        # print(reply)


def init_pools():
    global pool_for_checkit
    global pool_for_adm
    global camera_id_index
    global camera_url_index
    global camera_multicast_address_index
    global camera_number_index
    global camera_name_index
    global image_regions_index
    global matching_threshold_index
    global focus_value_threshold_index
    global light_level_threshold_index
    global slug_index
    global reference_image_id_index
    global reference_image_url_index
    global reference_image_index
    # print("PID %d: initializing pool..." % os.getpid())
    try:
        db_config_checkit = {
            "host": "localhost",
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        pool_for_checkit = MySQLConnectionPool(pool_name="pool_for_checkit",
                                               pool_size=10,
                                               **db_config_checkit)
        connection = pool_for_checkit.get_connection()
        checkit_cursor = connection.cursor()
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
        focus_value_threshold_index = field_names.index("focus_value_threshold")
        light_level_threshold_index = field_names.index("light_level_threshold")
        slug_index = field_names.index('slug')
        checkit_cursor.execute("SELECT * FROM main_menu_referenceimage LIMIT 1")
        checkit_result = checkit_cursor.fetchone()
        field_names = [i[0] for i in checkit_cursor.description]
        reference_image_id_index = field_names.index('id')
        reference_image_url_index = field_names.index('url_id')
        reference_image_index = field_names.index('image')
        connection.close()

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error("Invalid password on main database")
            exit(0)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logging.error("Database not initialised")
            exit(0)

    try:
        password = "0A21738C65FF283B4248D455633A9E98"
        adm_db_config = {
            "host": "localhost",
            "user": "root",
            "password": password,
            "database": "adm"
        }
        pool_for_adm = MySQLConnectionPool(pool_name="pool_for_adm",
                                           pool_size=1,
                                           **adm_db_config)
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error(f"Invalid password")
            exit(0)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logging.error(f"Database not initialised")
            exit(0)


def sql_insert(table, fields, values):
    try:
        sql_statement = "INSERT INTO " + table + " " + fields
        connection = pool_for_checkit.get_connection()
        checkit_cursor = connection.cursor()
        checkit_cursor.execute(sql_statement, values)
        connection.commit()
        checkit_cursor.close()
        connection.close()
    except mysql.connector.Error as e:
        logging.error(f"Database error during insert {e.msg}")
        print("Error message:", e.msg)


def sql_select(fields, table, where,  long_sql, fetch_all):
    try:
        if not long_sql:
            sql_statement = "SELECT " + fields + " FROM " + table + " " + where
        else:
            sql_statement = long_sql
        connection = pool_for_checkit.get_connection()
        checkit_cursor = connection.cursor()
        checkit_cursor.execute(sql_statement)
        if fetch_all:
            result = checkit_cursor.fetchall()
        else:
            result = checkit_cursor.fetchone()
        checkit_cursor.close()
        connection.close()
        return result
    except mysql.connector.Error as e:
        logging.error(f"Database error during select {e.msg}")
        print("Error message:", e.msg)


def sql_update(table, fields, where):
    sql_statement = "UPDATE " + table + " SET " + fields + where

    try:
        connection = pool_for_checkit.get_connection()
    except mysql.connector.PoolError as e:
        logging.error(f"Database error during update {e.msg}")
        print("Error message:", e.msg)
    finally:
        checkit_cursor = connection.cursor()
        checkit_cursor.execute(sql_statement)
        connection.commit()
        checkit_cursor.close()
        connection.close()


def sql_update_adm(table, fields, where):
    sql_statement = "UPDATE " + table + " SET " + fields + where

    try:
        connection = pool_for_adm.get_connection()
    except mysql.connector.PoolError as e:
        logging.error(f"Database error during update on admin {e.msg}")
        print("Error message:", e.msg)
    finally:
        checkit_cursor = connection.cursor()
        checkit_cursor.execute(sql_statement)
        connection.commit()
        checkit_cursor.close()
        connection.close()


def close_pool():
    connection = pool_for_checkit.get_connection()
    connection_pool = mysql.connector.pooling.PooledMySQLConnection(pool_for_checkit.pool_name, connection)
    connection_pool.close()


# def join_multicast(list_of_cameras):
#     db_connection = mysql.connector.connect(host="localhost",
#                                     user="checkit",
#                                     password="checkit",
#                                     database="checkit")
#
#     open_file = open(open_file_name, 'w')
#     close_file = open(close_file_name, 'w')
#
#
#
#     sql = "SELECT * FROM main_menu_camera WHERE id IN " + str(list_of_cameras).replace('[', '(').replace(']', ')')
#
#     checkit_cursor = db_connection.cursor()
#     checkit_cursor.execute(sql)
#     checkit_result = checkit_cursor.fetchall()
#
#     db_connection.close()
#
#     if checkit_result:
#
#         for record in checkit_result:
#             # print(record, camera_multicast_address_index)
#             multicast_address = record[camera_multicast_address_index]
#
#             if multicast_address:
#                 # print(record[camera_id_index], record[camera_multicast_address_index])
#                 open_command = "ip addr add " + multicast_address + "/32 dev " + network_interface + " autojoin"
#                 close_command = "ip addr del " + multicast_address + "/32 dev " + network_interface
#                 open_file.write(open_command + '\n')
#                 close_file.write(close_command + '\n')
#                 # print(open_command)
#     open_file.close()
#     close_file.close()
#     subprocess.call(['chmod', '+x', open_file_name])
#     subprocess.call(['chmod', '+x', close_file_name])
#     subprocess.call(['sudo', open_file_name])
#
#
# def un_join_multicast():
#     subprocess.call(['sudo', close_file_name])
#     logging.info(f"executing {close_file_name}")
#     subprocess.call(['rm', close_file_name, open_file_name])


def open_capture_device(record):

    if record[camera_multicast_address_index]:
        describe_uri = "DESCRIBE " + record[camera_url_index] + " RTSP/1.0\r\nCSeq: 2\r\n\r\n\r\n"
        camera_ip_address = describe_uri.split(" ")[1][7:].split("/")[0]
        rtsp_data = get_sdp.get_sdp(describe_uri)
        sdp_file_name = "/tmp/" + str(uuid.uuid4()) + ".sdp"

        if rtsp_data == "Error":
            logging.error(f"Error reading rtsp from camera {record[camera_url_index]}")
            try:
                os.remove(sdp_file_name)
            except OSError:
                pass

        else:
            with open(sdp_file_name, "w") as fd:
                for line in rtsp_data:
                    fd.write(line)
                    fd.write("\n")
                    # logging.info(f"wrote line {line} to {sdp_file_name}")
            fd.close()
            # if os.path.isfile(sdp_file_name):
            #     with open(sdp_file_name, "r") as fd:
            #         contents = fd.read()
            #         # logging.info(f"contents {contents}")
            # # logging.info(f"sdp file data {sdp_file_name}")
        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'add',
                             record[camera_multicast_address_index] + '/32', 'dev', network_interface, 'autojoin'])
        error_output = err.read()
        # not sure I need these next 2 lines.
        # with pipes() as (out, err):
        #     subprocess.call(['sudo', 'ip', 'a'])
        if error_output:
            logging.error(f"Unable to join multicast group - {error_output}")


        # try all 3 methods for rtsp_transport - this means users don't need to define the transport method
        # try:
        #     os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp_multicast'
        #     cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)
        # except cv2.error as err:
        #     logging.error(f"Error opening camera {record[camera_url_index]} ")
        try:
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'protocol_whitelist;file,rtp,udp'
            # cap = cv2.VideoCapture("rtsp://192.168.100.29/axis-media/media.amp", cv2.CAP_FFMPEG)
            cap = cv2.VideoCapture(sdp_file_name, cv2.CAP_FFMPEG)

        except cv2.error:
            logging.error(f"Unable to open stream for {record[camera_url_index]}")

        # try:
        #     os.remove(sdp_file_name)
        # except OSError:
        #     pass

        if not cap.isOpened():
            try:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
                cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)
            except cv2.error as err:
                logging.error(f"Error opening camera {record[camera_url_index]} ")

        if not cap.isOpened():
            try:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
                cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)
            except cv2.error as err:
                logging.error(f"Error opening camera {record[camera_url_index]} ")
    else:
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
        cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)
    return cap
    # describe_uri = "DESCRIBE " + record[camera_url_index] + " RTSP/1.0\r\nCSeq: 2\r\n\r\n\r\n"
    # camera_ip_address = describe_uri.split(" ")[1][7:].split("/")[0]
    # rtsp_data = get_sdp.get_sdp(describe_uri)
    # sdp_file_name = "/tmp/" + str(uuid.uuid4()) + ".sdp"
    # if record[camera_multicast_address_index]:
    #     if rtsp_data == "Error":
    #         logging.error(f"Error reading rtsp from camera {record[camera_url_index]}")
    #         if os.path.isfile(file_name):
    #             os.remove(file_name)
    #             return
    #         # may need to check return logic if error
    #     else:
    #         with open(file_name, "w") as fd:
    #             for line in rtsp_data:
    #                 fd.write(line)
    #                 fd.write("\n")
    #         fd.close()
    # else:
    #     os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
    #     cap = cv2.VideoCapture(record[camera_url_index], cv2.CAP_FFMPEG)
    # return cap


def close_capture_device(record, cap):
    cap.release()

    if record[camera_multicast_address_index]:
        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'del',
                             record[camera_multicast_address_index] + '/32', 'dev', network_interface])
        error_output = err.read()
        if error_output:
            logging.error(f"Unable to leave multicast group - {error_output}")
    # print("start of release")
    # cap.release()
    # print("end of release")

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
    # logging.info(scores)
    number_of_regions = len(r)
    scores.sort(reverse=True)
    sum_scores = sum(scores)

    scores_average = sum_scores / number_of_regions

    if len(r) > 0:
        full_ss = scores_average
    # if scores_average < full_ss:
    #     full_ss = scores_average
    full_ss = round(full_ss, 2)
    scores_average = round(scores_average, 2)

    fv = cv2.Laplacian(frame_color, cv2.CV_64F).var()
    fv = round(fv, 2)

    blur = cv2.blur(frame, (5, 5))
    frame_brightness = cv2.mean(blur)[0]
    blur = cv2.blur(base, (5, 5))
    base_brightness = cv2.mean(blur)[0]

    if is_low_contrast(frame, 0.25) or frame_brightness < 50:
        logging.info("Log image is of poor quality")
        full_ss = 0
    if is_low_contrast(base, 0.25) or base_brightness < 50:
        logging.info("Base image is of poor quality - please review reference images")
        full_ss = 0

    logging.debug(f"Match Score for full image is {full_ss}")
    logging.debug(f"Match Score for regions is {scores_average}")
    logging.debug(f"Focus value is {fv}")
    logging.debug(f"All region scores are {region_scores}")

    return full_ss, fv, region_scores, frame_brightness


def no_base_image(record):
    # connection = connection_pool.get_connection()
    # checkit_cursor = connection.cursor()
    logging.debug(f"No base image for {record}")
    capture_device = open_capture_device(record)

    if not capture_device.isOpened():
        logging.error(f"unable to open capture device {record[camera_url_index]}")
        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S")
        table = "main_menu_logimage"
        fields = "(url_id, image, matching_score, light_level, region_scores, current_matching_threshold, " \
                 "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        values = (str(record[camera_id_index]), "", "0", "0", "0", "0", "0", "Capture Error", now)
        sql_insert(table, fields, values)
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
                    try:
                        able_to_write = cv2.imwrite(file_name, frame)
                        if not able_to_write:
                            raise OSError
                        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        blur = cv2.blur(img_gray, (5, 5))
                        base_brightness = cv2.mean(blur)[0]

                        sql_file_name = file_name.strip("/home/checkit/camera_checker/media/")
                        table = "main_menu_referenceimage"
                        fields = "(url_id, image, hour, light_level) VALUES (%s,%s,%s,%s)"
                        values = (str(record[camera_id_index]), sql_file_name,
                                  time_stamp.strftime('%H'), base_brightness)
                        sql_insert(table, fields, values)
                    except OSError:
                        logging.error(f"Unable to save reference image {file_name}")
            except OSError as error:
                logging.error(f"Unable to create base image directory/file {error}")


def increment_transaction_count():
    table = "main_menu_licensing"
    fields = "transaction_count =  transaction_count + 1"
    where = " ORDER BY id DESC LIMIT 1"
    sql_update(table, fields, where)

    table = "adm"
    fields = "tx_count =  tx_count + 1"
    where = " ORDER BY id DESC LIMIT 1"
    sql_update_adm(table, fields, where)


def get_factorial():
    math.factorial(300000)


class ProcessCameras(object):

    def process_list(self, list_of_c):
        # logging.info(f"processing {list_of_c}, {pathos.helpers.mp.current_process()}")
        # logging.info(f"enter process_list")
        init_pools()
        # logging.info(f"list_of_c, {list_of_c}, {type(list_of_c)}")
        for camera in list_of_c:
            fields = "*"
            table = "main_menu_camera"
            where = "WHERE id = " + "\"" + str(camera) + "\""
            long_sql = None
            current_record = sql_select(fields, table, where, long_sql, fetch_all=False)
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
            hours = sql_select(fields, table, where, long_sql, fetch_all=True)
            int_hours = []
            # logging.info(f"hours, {hours}")
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
                    where = "WHERE url_id = " + "\"" + str(current_record[camera_id_index]) + \
                            "\"" + " AND hour = " + "\"" + closest_hour + "\""
                    long_sql = None
                    image = sql_select(fields, table, where, long_sql, fetch_all=False)
                    image = image[0]

                    base_image = "/home/checkit/camera_checker/media/" + image
                    if not os.path.isfile(base_image):
                        logging.error(f'Base image missing for {base_image}')
                        return

                    capture_device = open_capture_device(current_record)
                    # print("capture_device", type(capture_device))
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
                        time_stamp_string = datetime.datetime.strftime(time_stamp, "%Y-%m-%d %H:%M:%S")
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
                                logging.error(
                                    f"Image sizes don't match on camera number {current_record[camera_number_index]}")
                                now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S")
                                sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                                table = "main_menu_logimage"
                                fields = "(url_id, image, matching_score, light_level, region_scores, current_matching_threshold, " \
                                         "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                values = (str(current_record[camera_id_index]), sql_file_name,
                                          "0", "0", "{}", "0", "0", "Image Size Error", now)
                                sql_insert(table, fields, values)

                                increment_transaction_count()
                            else:
                                matching_score, focus_value, region_scores, frame_brightness = compare_images(
                                    image_base_grey,
                                    image_frame_grey,
                                    regions, image_base,
                                    image_frame)
                                sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")

                                if matching_score < current_record[matching_threshold_index]:
                                    action = "Failed"
                                    # logging.info("movement fail")
                                else:
                                    action = "Pass"

                                if action != "Failed":
                                    if focus_value < current_record[focus_value_threshold_index]:
                                        action = "Failed"
                                        # logging.info("focus fail")
                                    else:
                                        action = "Pass"

                                if action != "Failed":
                                    if frame_brightness < current_record[light_level_threshold_index]:
                                        action = "Failed"
                                        # logging.info("light fail")
                                    else:
                                        action = "Pass"

                                # print(focus_value, current_record[focus_value_threshold_index])


                                table = "main_menu_logimage"
                                fields = "(url_id, image, matching_score, region_scores, " \
                                         "current_matching_threshold, light_level, " \
                                         "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                values = (str(current_record[camera_id_index]), sql_file_name, float(matching_score),
                                          json.dumps(region_scores),
                                          float(current_record[matching_threshold_index]), float(frame_brightness),
                                          float(focus_value), action, time_stamp_string)
                                sql_insert(table, fields, values)

                                table = "main_menu_camera"
                                fields = "last_check_date = " + "\"" + time_stamp_string + "\""
                                where = " WHERE id = " + "\"" + str(current_record[camera_id_index]) + "\""
                                sql_update(table, fields, where)

                                increment_transaction_count()
                    else:
                        # print("unable to read")
                        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S")

                        table = "main_menu_logimage"
                        fields = "(url_id, image, matching_score, region_scores, " \
                                 "current_matching_threshold, light_level, focus_value, action, creation_date) " \
                                 "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                        values = (
                        str(current_record[camera_id_index]), "", "0", "{}", "0", "0", "0", "Capture Error", now)
                        sql_insert(table, fields, values)
                        increment_transaction_count()
            else:
                # only gets here with new camera
                logging.info(f"No base image for camera number {current_record[camera_number_index]} - "
                             f"{current_record[camera_name_index]}")
                no_base_image(current_record)
                increment_transaction_count()


def start_processes(list_of_cameras):
    pool = ProcessingPool(cpus*2)
    p = ProcessCameras()
    # logging.info(f"start_processes list {list_of_cameras} {type(list_of_cameras)} cpu's {cpus}")
    pool.imap(p.process_list, list_of_cameras)
    pool.close()
    pool.join()
    send_alarms(list_of_cameras)

# if __name__ == '__main__':
#     start_processes()
