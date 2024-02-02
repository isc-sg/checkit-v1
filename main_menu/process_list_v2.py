import sys

import cv2
import base64
import socket
import ipaddress
import re
import time
import logging
from logging.handlers import RotatingFileHandler
from wurlitzer import pipes
import subprocess
import os
import multiprocessing as mp
import mysql.connector
import threading
import concurrent.futures
from bisect import bisect_left
import datetime
import configparser
import itertools
from pathos.multiprocessing import cpu_count
import main_menu.a_eye
import main_menu.select_region
import pathlib
import json
from urllib.parse import urlparse
from urllib.parse import urlparse


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                    '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

list_of_lists = [[8359, 8360, 8361, 8362, 8363, 8364, 8365], [8366, 8367, 8368, 8369, 8370, 8371, 8372], [8373, 8374, 8375, 8376, 8377, 8378, 8379], [8380, 8381, 8382, 8383, 8384, 8385, 8386], [8387, 8388, 8389, 8390, 8391, 8392, 8393], [8394, 8395, 8396, 8397, 8398, 8399, 8400], [8401, 8402, 8403, 8404, 8405, 8406, 8407], [8408, 8409, 8410, 8411, 8412, 8413, 8414], [8415, 8416, 8417, 8418, 8419, 8420, 8421], [8422, 8423, 8424, 8425, 8426, 8427, 8428], [8429, 8430, 8431, 8432, 8433, 8434, 8435], [8436, 8437, 8438, 8439, 8440, 8441, 8442], [8443, 8444, 8445, 8446, 8447, 8448, 8449], [8450, 8451, 8452, 8453, 8454, 8455, 8456], [8457, 8458]]

# camera_file = open("/home/checkit/test_cameras.csv", "r")
# camera_lines: list = camera_file.readlines()

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

network_interface = "enp0s5"
socket_timeout = 1
camera_details_dict = {}
# this dictionary should contain camera_id(database record id): {parameters: value}
# example camera 22 in DB is record id 66
# {66: {"camera_name": "Entry Camera", "camera_number": 1, "url": "rtsp://1.2.3.4/"},
message_queue = mp.Queue()
cpus = cpu_count()


def get_camera_details(list_of_lists):
    try:
        if not list_of_lists:
            return "Error - camera list does not contain any cameras"
        db_config_checkit = {
            "host": "localhost",
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        checkit_db = mysql.connector.connect(**db_config_checkit)
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute("SELECT * FROM main_menu_camera LIMIT 1")
        fields_result = checkit_cursor.fetchone()
        field_names = [i[0] for i in checkit_cursor.description]

        merged_list = [item for sublist in list_of_lists for item in sublist]
        merged_list_string = str(merged_list).replace("[", "").replace("]", "")
        checkit_cursor.execute(f"SELECT * FROM main_menu_camera WHERE id IN ({merged_list_string})")
        checkit_result = checkit_cursor.fetchall()
        checkit_cursor.close()
        fields_dict = {}
        checkit_db.close()
        for result in checkit_result:
            for idx, field_name in enumerate(field_names):
                fields_dict[field_name] = result[idx]
            camera_details_dict[fields_dict['id']] = fields_dict
            fields_dict = {}

    except mysql.connector.Error as err:
        if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error("Invalid password on main database")
            return "Invalid password on main database"
            # consider not existing  ... this should exist with error code
        elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
            logging.error("Database not initialised")
            return "Checkit database not initialised"
        else:
            # print(err, "*",merged_list_string,"*")
            return err

    try:
        password = "C203EA1FF06AD85ECED4CC0568ACEF5F"
        adm_db_config = {
            "host": "localhost",
            "user": "root",
            "password": password,
            "database": "adm"
        }
        adm_db = mysql.connector.connect(**adm_db_config)
    except mysql.connector.Error as err:
        if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error(f"Invalid password")
            return "Invalid password on admin database"
            # TODO - this exit doesn't close properly when run from start.py
        elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
            logging.error(f"Database not initialised")
            return "Admin database not initialised"
    return camera_details_dict

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


def extract_ip_from_url(url):
    output = urlparse(url)
    ip_address = output.hostname
    scheme = output.scheme
    # use try to catch cases where url_port is non-numeric in url - if so then default to 554
    try:
        url_port = output.port
    except ValueError:
        url_port = 554
    # if url_port is None then default to 554
    if not url_port:
        port_number = 554
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        logging.error(f"Invalid IP address in {url}")
        ip_address = "Error"
    return ip_address, url_port, scheme


def check_uri(uri):
    ip_address, url_port, scheme = extract_ip_from_url(uri)

    try:
        ipaddress.ip_address(ip_address)

    except ValueError:
        # print((colored("Invalid IP address" + str(uri), 'red', attrs=['reverse', 'blink'])))
        logging.error(f"Invalid IP address {uri}")
        # print needs to be changed to logging
        return "Error"
    return ip_address, url_port, scheme


def options(url, ip_address, url_port, username=None, password=None):
    error_flag = False


    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(socket_timeout)
        s.connect((ip_address, url_port))
        request = f"OPTIONS {url} RTSP/1.0\r\nCSeq: 0\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        if response[0] != "RTSP/1.0 200 OK":
            error_flag = True
        s.close()
    except socket.timeout:
        response = f"Timed out connecting to device on {url}"
        error_flag = True
    except socket.error as error:
        # print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        # logging.error(f"Error connecting to device {uri}")
        response = f"Error connecting to device {error}"
        error_flag = True

    return response, error_flag


def setup(uri,  username=None, password=None):
    error_flag = False
    transport = None
    ip_address, url_port, scheme = check_uri(uri)
    if scheme != "rtsp":
        return scheme, "NON RTSP", True, None

    # check SETUP assuming multicast  - UDP is underlying transport
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(socket_timeout)
        s.connect((ip_address, url_port))
        request = f"SETUP {uri} RTSP/1.0\r\nCSeq: 1\r\n"
        request += "Transport: RTP/AVP;multicast\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        s.close()
        if response[0] == "RTSP/1.0 200 OK":
            for response_line in response:
                if response_line.startswith("Transport: "):
                    describe_parameters = response_line.split("Transport: ")[1].split(";")
                    if describe_parameters[1] == "unicast":
                        transport = "UNICAST/UDP"
                    elif describe_parameters[1] == "multicast":
                        transport = "MULTICAST"

        # check SETUP assuming unicast and TCP as underlying transport
        if response[0] != "RTSP/1.0 200 OK":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((ip_address, url_port))
                request = f"SETUP {uri} RTSP/1.0\r\nCSeq: 1\r\n"
                request += "Transport: RTP/AVP;unicast\r\n"
                request += add_auth(username=username, password=password)
                request += "\r\n"
                s.sendall(request.encode())
                data = s.recv(1024).decode()
                response = data.split("\r\n")
                s.close()
                if response[0] == "RTSP/1.0 200 OK":
                    transport = "UNICAST/TCP"
            except socket.error:
                pass

        # check SETUP assuming unicast and UDP as underlying transport
        if response[0] != "RTSP/1.0 200 OK":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((ip_address, url_port))
                request = f"SETUP {uri} RTSP/1.0\r\nCSeq: 1\r\n"
                request += "Transport: RTP/AVP/UDP;unicast\r\n"
                request += add_auth(username=username, password=password)
                request += "\r\n"
                s.sendall(request.encode())
                data = s.recv(1024).decode()
                response = data.split("\r\n")
                s.close()
                if response[0] == "RTSP/1.0 200 OK":
                    transport = "UNICAST/UDP"
            except socket.error:
                pass
        if response[0] != "RTSP/1.0 200 OK":
            error_flag = True

    except socket.error:
        # logging.error(f"Error connecting to device {uri}")
        response = "Error connecting to device"
        error_flag = True

    return scheme, response, error_flag, transport


def describe(url, ip_address, url_port, username=None, password=None):
    error_flag = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(socket_timeout)
        s.connect((ip_address, url_port))
        request = f"DESCRIBE {url} RTSP/1.0\r\nCSeq: 0\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        s.close()
        if response[0] != "RTSP/1.0 200 OK":
            error_flag = True
    except socket.timeout:
        # print((colored("Error connecting to device " + str(url), 'red', attrs=['reverse', 'blink'])))
        # logging.error(f"Timed out connecting to device {url}")
        response = f"Timed out connecting to device {url}"
        error_flag = True
    except socket.error as error:
        # print((colored("Error connecting to device " + str(url), 'red', attrs=['reverse', 'blink'])))
        # logging.error(f"Error connecting to device {url}")
        response = f"Error connecting to device {url} - {error}"
        error_flag = True

    return response, error_flag


def open_capture_device(url, multicast_address, multicast_port, describe_data):
    # logging.info(f"{url}{multicast_address}{multicast_port}{describe_data}")
    if multicast_address:
        # let's ignore the url_port here - use the port configured in the database.  The port here is in fact
        # the rtsp servers port
        ip_address, url_port, scheme = extract_ip_from_url(url)
        if not ip_address:
            logging.error(f"Error in URL for camera url {url}")
            return "Error"

        # remove all lines that are not sdp file compliant - must have single_char then =
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
                        # video_c_parameter = fixed_entry[2:]

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
                logging.error(f"Error opening camera {url} - {err} ")

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


def logging_queue():
    message = None
    # print(message)
    print("Started Logger")

    while message != "End":
        message = message_queue.get()
        # if message != "End":
        #     print(message)
        # print(message)
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
        creation_date = datetime.datetime.strftime(i[1], "%Y-%m-%d %H:%M:%S.%f")
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


def sql_insert(table, fields, values):
    try:
        db_config_checkit = {
            "host": "localhost",
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        checkit_db = mysql.connector.connect(**db_config_checkit)
        sql_statement = "INSERT INTO " + table + " " + fields

        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement, values)
        checkit_db.commit()
        checkit_cursor.close()
        checkit_db.close()
    except mysql.connector.Error as e:
        logging.error(f"Database error during insert {e.msg}")
        print("Error message:", e.msg)


def sql_select(fields, table, where,  long_sql, fetch_all):

    try:
        db_config_checkit = {
            "host": "localhost",
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        checkit_db = mysql.connector.connect(**db_config_checkit)
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
        checkit_db.close()
        return result
    except mysql.connector.Error as e:
        logging.error(f"Database error during select {e.msg}")
        print("Error message:", e.msg)


def sql_update(table, fields, where):

    sql_statement = "UPDATE " + table + " SET " + fields + where

    try:
        db_config_checkit = {
            "host": "localhost",
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        checkit_db = mysql.connector.connect(**db_config_checkit)
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement)
        checkit_db.commit()
        checkit_cursor.close()
        checkit_db.close()
    except mysql.connector.errors as e:
        logging.error(f"Database error during update {e.msg}")
        print("Error message:", e.msg)


def sql_update_adm(table, fields, where):

    sql_statement = "UPDATE " + table + " SET " + fields + where

    try:
        password = "C203EA1FF06AD85ECED4CC0568ACEF5F"
        adm_db_config = {
            "host": "localhost",
            "user": "root",
            "password": password,
            "database": "adm"
        }
        adm_db = mysql.connector.connect(**adm_db_config)
        adm_cursor = adm_db.cursor()
        adm_cursor.execute(sql_statement)
        adm_db.commit()
        adm_cursor.close()
        adm_db.close()
    except mysql.connector.PoolError as e:
        logging.error(f"Database error during update on admin {e.msg}")
        print("Error message:", e.msg)


def increment_transaction_count():
    table = "main_menu_licensing"
    fields = "transaction_count =  transaction_count + 1"
    where = " ORDER BY id DESC LIMIT 1"
    sql_update(table, fields, where)

    table = "adm"
    fields = "tx_count =  tx_count + 1"
    where = " ORDER BY id DESC LIMIT 1"
    sql_update_adm(table, fields, where)


def compare_images(base, frame, r, base_color, frame_color):
    h, w = frame.shape[:2]
    all_regions = []
    all_regions.extend(range(1, 65))
    region_scores = {}
    coordinates = main_menu.select_region.get_coordinates(all_regions, h, w)
    scores = []
    # full_ss = movement(base, frame)
    frame_equalised = cv2.equalizeHist(frame)
    frame_bilateral = cv2.bilateralFilter(frame_equalised, 9, 100, 100)
    base_equalised = cv2.equalizeHist(base)
    base_bilateral = cv2.bilateralFilter(base_equalised, 9, 100, 100)
    full_ss = main_menu.a_eye.movement(base_bilateral, frame_bilateral)
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
            ss = main_menu.a_eye.movement(sub_img_base, sub_img_frame)
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


def no_base_image(camera, describe_data):
    # connection = connection_pool.get_connection()
    # checkit_cursor = connection.cursor()
    logging.info(f"Capturing base image for {camera_details_dict[camera]['url']}")
    capture_device = open_capture_device(url=camera_details_dict[camera]['url'],
                                         multicast_address=camera_details_dict[camera]['multicast_address'],
                                         multicast_port=camera_details_dict[camera]['multicast_port'],
                                         describe_data=describe_data)

    if not capture_device.isOpened() or capture_device == "Error":
        logging.error(f"unable to open capture device {camera_details_dict[camera]['url']}")
        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
        table = "main_menu_logimage"
        fields = "(url_id, image, matching_score, light_level, region_scores, current_matching_threshold, " \
                 "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        values = (str(camera), "", "0", "0", "0", "0", "0", "Capture Error", now)
        sql_insert(table, fields, values)
        close_capture_device(capture_device, camera_details_dict[camera]['multicast_address'])
        return
    else:
        try:
            able_to_read, frame = capture_device.read()
            if not able_to_read:
                # raise NameError()
                logging.error(f"Unable to read from device for camera id {camera} / camera number {camera_details_dict[camera]['camera_number']}")

        except cv2.error as e:
            logging.error(f"cv2 error {e}")
        # except NameError:
        #     logging.error(f"Unable to read camera {camera_details_dict[camera]['camera_number']} - "
        #                   f"{camera_details_dict[camera]['camera_name']}")
        else:
            logging.debug(f"Able to capture base image on {camera_details_dict[camera]['camera_name']}")
            time_stamp = datetime.datetime.now()
            file_name = "/home/checkit/camera_checker/media/base_images/" + str(camera) + "/" + \
                        time_stamp.strftime('%H') + ".jpg"
            directory = "/home/checkit/camera_checker/media/base_images/" + str(camera)
            try:
                pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                if os.path.isfile(file_name):
                    os.remove(file_name)
                else:
                    try:
                        able_to_write = cv2.imwrite(file_name, frame)
                        if not able_to_write:
                            logging.error(f"Unable to save reference image for id {camera} / "
                                          f" camera number {camera_details_dict[camera]['camera_number']}")
                        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        blur = cv2.blur(img_gray, (5, 5))
                        base_brightness = cv2.mean(blur)[0]

                        sql_file_name = file_name.strip("/home/checkit/camera_checker/media/")
                        table = "main_menu_referenceimage"
                        fields = "(url_id, image, hour, light_level) VALUES (%s,%s,%s,%s)"
                        values = (str(camera), sql_file_name,
                                  time_stamp.strftime('%H'), base_brightness)
                        sql_insert(table, fields, values)
                    except:
                        logging.error(f"Unable to save reference image {file_name}")

            except Exception as error:
                logging.error(f"Unable to create base image directory/file {error}")
            close_capture_device(capture_device, camera_details_dict[camera]['multicast_address'])


def check(cameras):

    for camera in cameras:
        url = camera_details_dict[camera]['url']
        camera_number = camera_details_dict[camera]['camera_number']
        multicast_address = camera_details_dict[camera]['multicast_address']
        multicast_port = camera_details_dict[camera]['multicast_port']
        camera_username = camera_details_dict[camera]['camera_username']
        camera_password = camera_details_dict[camera]['camera_password']
        current_light_level = camera_details_dict[camera]['light_level_threshold']
        current_focus_value = camera_details_dict[camera]['focus_value_threshold']
        message = f"Attempting connection to {url}\n"

        # print(f"Attempting connection to {url}")
        if camera_username and camera_password:
            url_parts = url.split("//")
            url = f"{url_parts[0]}//{camera_username}:{camera_password}@{url_parts[1]}"
        # print("Start OPTIONS")
        check_time = time.time()

        has_error = False
        ip_address, url_port, scheme = extract_ip_from_url(url)

        if scheme == "rtsp":
            options_response, has_error = options(url, ip_address, url_port, camera_username, camera_password)

            if not has_error:
                message = message + f"Connected to {url}\n"
            else:
                message = message + f"Error inb OPTIONS for {url} {options_response}\n"
                now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
                table = "main_menu_logimage"
                fields = "(url_id, image, matching_score, region_scores, " \
                         "current_matching_threshold, focus_value, " \
                         "current_focus_value, light_level, current_light_level, action, " \
                         "creation_date) " \
                         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error", now)
                sql_insert(table, fields, values)
                increment_transaction_count()
                message_queue.put(message)
                continue

            describe_response, has_error = describe(url, ip_address, url_port, camera_username, camera_password)
            if has_error:
                message = message + f"Error in DESCRIBE for url {url} {describe_response}"
                now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
                table = "main_menu_logimage"
                fields = "(url_id, image, matching_score, region_scores, " \
                         "current_matching_threshold, focus_value, " \
                         "current_focus_value, light_level, current_light_level, action, " \
                         "creation_date) " \
                         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error", now)
                sql_insert(table, fields, values)
                increment_transaction_count()
                message = message + f"{describe_response}\n"

        if not has_error:
            capture_device = open_capture_device(url, multicast_address, multicast_port, describe_response)
            if capture_device != "Error":
                if not capture_device.isOpened():
                    # print(f"Capture device not opened for {url}")
                    # message = message + f"Capture device not opened for {url}"
                    # logging.error(f"Capture device not opened for {url}")
                    now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")

                    table = "main_menu_logimage"
                    fields = "(url_id, image, matching_score, region_scores, " \
                             "current_matching_threshold, focus_value, " \
                             "current_focus_value, light_level, current_light_level, action, " \
                             "creation_date) " \
                             "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error", now)
                    sql_insert(table, fields, values)
                    increment_transaction_count()
                    # print("Error reading video frame")
                    message = message + f"Unable to open capture device {url}\n"
                if capture_device.isOpened():

                    able_to_read, image_frame = capture_device.read()

                    close_capture_device(capture_device, multicast_address)
                    if able_to_read:
                        # first lets make sure the image_regions parameter is correctly set
                        regions = camera_details_dict[camera]['image_regions']
                        if regions == '0' or regions == "[]":
                            regions = []
                            regions.extend(range(1, 65))
                        else:
                            regions = eval(regions)

                        # check if the camera has hours set in the schedules
                        current_time = datetime.datetime.now()
                        current_hour = current_time.strftime('%H')
                        fields = "hour"
                        table = "main_menu_referenceimage"
                        where = "WHERE url_id = " + "\"" + str(camera) + "\""
                        long_sql = None
                        captured_reference_hours = sql_select(fields, table, where, long_sql, fetch_all=True)
                        scheduled_hours = []
                        # logging.info(f"hours,{camera} {captured_reference_hours} ")

                        if captured_reference_hours:

                            for i in range(0, len(captured_reference_hours)):
                                scheduled_hours.append(captured_reference_hours[i][0])
                                scheduled_hours[i] = int(scheduled_hours[i])

                            current_hour = int(current_hour)

                            if current_hour not in scheduled_hours:
                                no_base_image(camera, describe_response)
                                increment_transaction_count()
                                continue

                            else:
                                # get the base image for the current camera at the current hour
                                closest_hour = take_closest(scheduled_hours, current_hour)
                                closest_hour = str(closest_hour).zfill(2)
                                fields = "image"
                                table = "main_menu_referenceimage"
                                where = "WHERE url_id = " + "\"" + str(camera) + \
                                        "\"" + " AND hour = " + "\"" + closest_hour + "\""
                                long_sql = None
                                image = sql_select(fields, table, where, long_sql, fetch_all=False)
                                image = image[0]
                                base_image_location = "/home/checkit/camera_checker/media/" + image

                                # check that the image actually exists on the filesystem
                                if not os.path.isfile(base_image_location):
                                    logging.error(f'Base image missing for {base_image_location}')
                                    increment_transaction_count()
                                    continue

                                # read it
                                base_image = cv2.imread(base_image_location)

                                # save log image
                                time_stamp = datetime.datetime.now()
                                time_stamp_string = datetime.datetime.strftime(time_stamp, "%Y-%m-%d %H:%M:%S.%f")
                                directory = "/home/checkit/camera_checker/media/logs/" + str(time_stamp.year) + "/" + \
                                            str(time_stamp.month) + "/" + str(time_stamp.day)
                                log_image_file_name = directory + "/" + str(camera) + \
                                                      "-" + str(time_stamp.hour) + ":" + str(time_stamp.minute) + ":" + \
                                                      str(time_stamp.second) + ".jpg"
                                # attempt to save log file
                                try:
                                    pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                                except OSError as error:
                                    logging.error(f"Error saving log file {error}")
                                    increment_transaction_count()
                                    continue

                                able_to_write = cv2.imwrite(log_image_file_name, image_frame)
                                capture_dimensions = image_frame.shape[:2]
                                reference_dimensions = ()
                                status = "failed"

                                if not able_to_write:
                                    logging.error(f"Unable to write log image {log_image_file_name}")
                                    increment_transaction_count()
                                    continue
                                else:
                                    try:
                                        image_base_grey = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
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
                                            f"Image sizes don't match on camera number {camera}")
                                        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
                                        sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                                        table = "main_menu_logimage"
                                        fields = "(url_id, image, matching_score, region_scores, " \
                                                 "current_matching_threshold, focus_value, " \
                                                 "current_focus_value, light_level, current_light_level, action, " \
                                                 "creation_date) " \
                                                 "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                        values = (
                                        str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error", now)
                                        sql_insert(table, fields, values)
                                        increment_transaction_count()
                                        continue
                                    else:
                                        # this is the actual comparison section
                                        (matching_score,
                                         focus_value,
                                         region_scores,
                                         frame_brightness) = compare_images(image_base_grey,
                                                                            image_frame_grey,
                                                                            regions, base_image,
                                                                            image_frame)
                                        sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")

                                        if matching_score < camera_details_dict[camera]['matching_threshold']:
                                            action = "Failed"
                                            # logging.info("movement fail")
                                        else:
                                            action = "Pass"

                                        if action != "Failed":
                                            if focus_value < camera_details_dict[camera]['focus_value_threshold']:
                                                action = "Failed"
                                                # logging.info("focus fail")
                                            else:
                                                action = "Pass"

                                        if action != "Failed":
                                            if frame_brightness < camera_details_dict[camera]['light_level_threshold']:
                                                action = "Failed"
                                                # logging.info("light fail")
                                            else:
                                                action = "Pass"

                                        table = "main_menu_logimage"
                                        fields = "(url_id, image, matching_score, region_scores, " \
                                                 "current_matching_threshold, light_level, " \
                                                 "focus_value, action, creation_date, " \
                                                 "current_focus_value, current_light_level) " \
                                                 "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                        values = (
                                                  str(camera),
                                                  sql_file_name,
                                                  float(matching_score),
                                                  json.dumps(region_scores),
                                                  float(camera_details_dict[camera]['matching_threshold']),
                                                  float(frame_brightness),
                                                  float(focus_value),
                                                  action,
                                                  time_stamp_string,
                                                  float(camera_details_dict[camera]['focus_value_threshold']),
                                                  float(camera_details_dict[camera]['light_level_threshold'])
                                        )

                                        sql_insert(table, fields, values)

                                        table = "main_menu_camera"
                                        fields = "last_check_date = " + "\"" + time_stamp_string + "\""
                                        where = " WHERE id = " + "\"" + str(camera) + "\""
                                        sql_update(table, fields, where)
                                        increment_transaction_count()
                        else:
                            no_base_image(camera,describe_response)
                            increment_transaction_count()
                            # image_frame = cv2.resize(image_frame,(960,540))
                            # cv2.imshow("image", image_frame)
                            # cv2.waitKey(50)
                            # message = message + f"Writting to /tmp/{camera_number}.jpg"
                            # cv2.imwrite(f"/tmp/{camera_number}.jpg", image_frame)
                    if not able_to_read:
                        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")

                        table = "main_menu_logimage"
                        fields = "(url_id, image, matching_score, region_scores, " \
                                 "current_matching_threshold, focus_value, " \
                                 "current_focus_value, light_level, current_light_level, action, " \
                                 "creation_date) " \
                                 "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                        values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error", now)
                        sql_insert(table, fields, values)
                        increment_transaction_count()
                        # print("Error reading video frame")
                        message = message + "Error reading video frame\n"
                else:
                    # logging.error(f"Unable to open capture device {url}")
                    now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")

                    table = "main_menu_logimage"
                    fields = "(url_id, image, matching_score, region_scores, " \
                             "current_matching_threshold, focus_value, " \
                             "current_focus_value, light_level, current_light_level, action, " \
                             "creation_date) " \
                             "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error", now)
                    sql_insert(table, fields, values)
                    increment_transaction_count()
                    # print("Error reading video frame")
                    message = message + f"Unable to open capture device {url}\n"
            else:
                now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
                table = "main_menu_logimage"
                fields = "(url_id, image, matching_score, region_scores, " \
                         "current_matching_threshold, focus_value, " \
                         "current_focus_value, light_level, current_light_level, action, " \
                         "creation_date) " \
                         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error", now)
                sql_insert(table, fields, values)
                increment_transaction_count()
                # print("Error reading video frame")
                message = message + f"Unable to open capture device {url}\n"
        message_queue.put(message)


logging_process = mp.Process(target=logging_queue)
logging_process.start()

# check(merged_list)
# message_queue.put("End")


def start_processes(list_of_lists):
    camera_details_dict = get_camera_details(list_of_lists)
    if not isinstance(camera_details_dict, dict):
        message_queue.put(camera_details_dict)
        message_queue.put("End")
        sys.exit(1)
    with mp.Pool(16) as p:
        start_time = time.time()
        p.map(check, list_of_lists)
        p.close()
        p.join()
        # print("finished")
        # message_queue.put("End")
        # print("Total time", round(time.time() - start_time, 2))


if __name__ == "__main__":
    camera_details_dict = get_camera_details(list_of_lists)

    for item in list_of_lists:
        check(item)
    message_queue.put("End")
