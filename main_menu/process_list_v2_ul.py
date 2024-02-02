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
import ipaddress
import base64
from termcolor import colored
import re
import multiprocessing as mp

# open_file_name = '/tmp/' + str(uuid.uuid4().hex)
# close_file_name = '/tmp/' + str(uuid.uuid4().hex)


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

config = configparser.ConfigParser()
config.read('/home/checkit/camera_checker/main_menu/config/config.cfg')

socket_timeout = 1
message_queue = mp.Queue()


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


def add_auth(username, password):
    if username:
        # Combine username and password into a single string
        credentials = f"{username}:{password}"
        # Encode credentials in Base64
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        # Add the Authorization header
        return f"Authorization: Basic {encoded_credentials}\r\n"
    else:
        return ""


def extract_ip_from_rtsp_url(rtsp_url):
    # Define a regular expression pattern to match IP addresses
    ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'

    # Define a regular expression pattern to match the RTSP protocol part
    protocol_pattern = r'rtsp://'

    # Define a regular expression pattern to match the username:password part
    auth_pattern = r'(?:\S+:\S+@)?'
    # auth_pattern = r'(?:[^@]*@)?'

    # Define a regular expression pattern to match the port number part
    port_pattern = r'(?::\d+)?'

    # Combine the patterns to create a full regular expression
    rtsp_pattern = f'{protocol_pattern}{auth_pattern}({ip_pattern}){port_pattern}(/.*)?'

    # Use re.search to find the IP address in the URL
    match = re.search(rtsp_pattern, rtsp_url)

    if match:
        ip_address = match.group(1)
        return ip_address
    else:
        return None


def check_uri(uri):
    camera_ip_address = extract_ip_from_rtsp_url(uri)

    try:
        ipaddress.ip_address(camera_ip_address)
    except ValueError:
        # print((colored("Invalid IP address" + str(uri), 'red', attrs=['reverse', 'blink'])))
        logging.error(f"Invalid IP address {uri}")
        # print needs to be changed to logging
        return "Error"
    return camera_ip_address

def options(uri, username=None, password=None):
    error_flag = False
    camera_ip_address = check_uri(uri)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(socket_timeout)
        s.connect((camera_ip_address, 554))
        request = f"OPTIONS {uri} RTSP/1.0\r\nCSeq: 0\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        if response[0] != "RTSP/1.0 200 OK":
            error_flag = True
        s.close()
    except socket.timeout:
        # print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        logging.error(f"Timed out connecting to device {uri}")
        response = f"Timed out connecting to device {uri}"
        error_flag = True
    except socket.error as error:
        # print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        logging.error(f"Error connecting to device {uri}")
        response = f"Error connecting to device {error}"
        error_flag = True

    return response, error_flag

def describe(uri, username=None, password=None):
    error_flag = False
    camera_ip_address = check_uri(uri)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(socket_timeout)
        s.connect((camera_ip_address, 554))
        request = f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 0\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        s.close()
        if response[0] != "RTSP/1.0 200 OK":
            error_flag = True
    except socket.timeout:
        # print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        logging.error(f"Timed out connecting to device {uri}")
        response = f"Timed out connecting to device {uri}"
        error_flag = True
    except socket.error as error:
        # print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        logging.error(f"Error connecting to device {uri}")
        response = f"Error connecting to device {uri} - {error}"
        error_flag = True

    return response, error_flag


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
    global camera_multicast_port_index
    global camera_username_index
    global camera_password_index
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
                                               pool_size=1,
                                               **db_config_checkit)
        connection = pool_for_checkit.get_connection()
        checkit_cursor = connection.cursor()
        checkit_cursor.execute("SELECT * FROM main_menu_camera LIMIT 1")
        checkit_result = checkit_cursor.fetchone()
        field_names = [i[0] for i in checkit_cursor.description]
        camera_id_index = field_names.index('id')
        camera_url_index = field_names.index('url')
        camera_multicast_address_index = field_names.index('multicast_address')
        camera_multicast_port_index = field_names.index("multicast_port")
        camera_username_index = field_names.index('camera_username')
        camera_password_index = field_names.index('camera_password')
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
        password = "7F8129340F252052FE8B81A60466763B"
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
#     subprocess.call(['rm', close_file_name, open_file_name])


def open_capture_device(url, multicast_address, multicast_port, describe_data):

    if multicast_address:

        ip_address = extract_ip_from_rtsp_url(url)
        if not ip_address:
            logging.error(f"Error in URL for camera url {url}")
            return "Error"

        describe_data = [item for item in describe_data if len(item) >= 2 and item[1] == "="]

        port = None
        inside_video_section = False
        video_a_parameters = {}
        video_c_parameter = None
        control = None

        for index, line in enumerate(describe_data):

            # Check for the start of the video section (m=video)
            if line.startswith("a="):
                key = line[2:].split(":")
                # need to cater for cases where multiple ":" exist eg a=control:rtsp://1.1.1.1:554/h264
                if key[0] == "control":
                    # join the remainder of the values in key to be value
                    value = ":".join(key[1:])
                    if url in value:
                        control = value.split(url)[1][1:]
                    else:
                        control = value
            if line.startswith("m=video"):
                inside_video_section = True
                port = line.split()[1]
                if multicast_address and multicast_port:
                    if port == "0":
                        fixed_entry = line.replace("m=video 0", f"m=video {multicast_port}")
                        describe_data[index] = fixed_entry
                # print("Port number", port)
                continue

            if line.startswith("m=") and inside_video_section:
                inside_video_section = False
                break
            if inside_video_section and line.startswith("c="):
                video_c_parameter = line[2:]
                if multicast_address:
                    if video_c_parameter.split(" ")[-1] == "0.0.0.0":
                        fixed_entry = line.replace("0.0.0.0", multicast_address)
                        describe_data[index] = fixed_entry
                        video_c_parameter = fixed_entry[2:]

            if inside_video_section and line.startswith("a="):
                # video_a_parameters.append(line[2:])
                try:
                    key, value = line[2:].split(":")
                    video_a_parameters[key] = value

                    if key == "control":
                        if url in value:
                            control = value.split(url)[2]
                        else:
                            control = value

                except ValueError:
                    video_a_parameters[line[2:]] = True

        with open(f"/tmp/{ip_address}.sdp", "w") as fd:

            for line in describe_data:
                fd.write(line + "\n")
        fd.close()

        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'add',
                             multicast_address + '/32', 'dev', network_interface, 'autojoin'])
        error_output = err.read()
        if "File exists" not in error_output:
            if error_output:
                logging.error(f"Unable to join multicast group - {error_output}")
                try:
                    os.remove(f"/tmp/{ip_address}.sdp")
                except OSError:
                    pass
                return "Error"
        cap = None
        try:
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'protocol_whitelist;file,rtp,udp'
            cap = cv2.VideoCapture(f"/tmp/{ip_address}.sdp", cv2.CAP_FFMPEG)
        except cv2.error:
            logging.error(f"Unable to open session description file for {url}")
            try:
                os.remove(f"/tmp/{ip_address}.sdp")
            except OSError:
                pass

        try:
            os.remove(f"/tmp/{ip_address}.sdp")
        except OSError:
            pass

        if not cap.isOpened():
            try:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            except cv2.error as err:
                logging.error(f"Error opening camera {url} - {err}")

        if not cap.isOpened():
            try:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            except cv2.error as err:
                logging.error(f"Error opening camera {url} - {err}")
                return "Error"
    else:
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            return "Error"

    return cap

def display_queue():
    message = None
    while message != "End":
        message = message_queue.get()
        if message != "End":
            logging.info(message)


def close_capture_device(cap, multicast_address):
    cap.release()

    if multicast_address:
        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'del',
                             multicast_address + '/32', 'dev', network_interface])
        error_output = err.read()
        if error_output:
            logging.error(f"Unable to leave multicast group - {error_output}")


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
    # base_brightness = cv2.mean(blur)[0]

    # if is_low_contrast(frame, 0.25) or frame_brightness < 50:
    #     logging.info("Log image is of poor quality")
    #     full_ss = 0
    # if is_low_contrast(base, 0.25) or base_brightness < 50:
    #     logging.info("Base image is of poor quality - please review reference images")
    #     full_ss = 0

    logging.debug(f"Match Score for full image is {full_ss}")
    logging.debug(f"Match Score for regions is {scores_average}")
    logging.debug(f"Focus value is {fv}")
    logging.debug(f"All region scores are {region_scores}")

    return full_ss, fv, region_scores, frame_brightness


def no_base_image(record, describe_data):
    # connection = connection_pool.get_connection()
    # checkit_cursor = connection.cursor()
    logging.info(f"Capturing base image for {record[camera_url_index]}")
    capture_device = open_capture_device(url=record[camera_url_index],
                                         multicast_address=record[camera_multicast_address_index],
                                         multicast_port=record[camera_multicast_port_index],
                                         describe_data=describe_data)

    if not capture_device.isOpened() or capture_device == "Error":
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
            close_capture_device(record, capture_device)


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
        logging.info(f"processing {list_of_c}, {pathos.helpers.mp.current_process()}")
        # logging.info(f"enter process_list")
        init_pools()
        # logging.info(f"list_of_c, {list_of_c}, {type(list_of_c)}")
        for camera in list_of_c:
            logging.info(f"Doing camera {camera}")
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
            url = current_record[camera_url_index]
            multicast_address = current_record[camera_multicast_address_index]
            multicast_port = current_record[camera_multicast_port_index]
            user_name = current_record[camera_username_index]
            user_password = current_record[camera_password_index]
            current_time = datetime.datetime.now()
            hour = current_time.strftime('%H')
            fields = "hour"
            table = "main_menu_referenceimage"
            where = "WHERE url_id = " + "\"" + str(current_record[camera_id_index]) + "\""
            long_sql = None
            hours = sql_select(fields, table, where, long_sql, fetch_all=True)
            int_hours = []
            logging.info(f"hours,{camera} {hours} ")
            if hours:
                for i in range(0, len(hours)):
                    int_hours.append(hours[i][0])
                    int_hours[i] = int(int_hours[i])
                hour = int(hour)
                if hour not in int_hours:
                    options_response, error_flag = options(url, user_name, user_password)
                    if error_flag:
                        logging.info(f"Error connecting to RTSP OPTIONS on camera {url}")
                        continue
                    describe_data, error_flag = describe(url, user_name, user_password)
                    if error_flag:
                        logging.info(f"Error connecting to RTSP DESCRIBE on camera {url}")
                        continue
                    no_base_image(current_record, describe_data)
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
                        continue

                    options_response, error_flag = options(url, user_name, user_password)
                    if error_flag:
                        logging.info(f"Error connecting to RTSP OPTIONS on camera {url}")
                        continue
                    describe_data, error_flag = describe(url, user_name, user_password)
                    if error_flag:
                        logging.info(f"Error connecting to RTSP DESCRIBE on camera {url}")
                        continue
                    capture_device = open_capture_device(url,
                                                         multicast_address,
                                                         multicast_port,
                                                         describe_data)
                    able_to_read = False
                    if capture_device != "Error":
                        if capture_device.isOpened():
                            able_to_read, image_frame = capture_device.read()
                            close_capture_device(current_record, capture_device)
                    else:
                        logging.error(f"Unable to open capture device {url}")
                        continue

                    if able_to_read:
                        image_base = cv2.imread(base_image)
                        if image_base is None:
                            logging.error(f"Base image is logged but unable to file {base_image}")
                            continue
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
                            continue

                        able_to_write = cv2.imwrite(log_image_file_name, image_frame)
                        capture_dimensions = image_frame.shape[:2]
                        reference_dimensions = ()
                        status = "failed"

                        if not able_to_write:
                            logging.error(f"Unable to write log image {log_image_file_name}")
                            continue

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
                                continue

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
                                continue
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
                logging.info(f"No base image for camera number {camera} - {current_record[camera_number_index]} - "
                             f"{current_record[camera_name_index]}")
                options_response, error_flag = options(url, user_name, user_password)
                if error_flag:
                    logging.info(f"Error connecting to RTSP OPTIONS on camera {url}")
                    continue
                describe_data, error_flag = describe(url, user_name, user_password)
                if error_flag:
                    logging.info(f"Error connecting to RTSP DESCRIBE on camera {url}")
                    continue
                no_base_image(current_record, describe_data)
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
