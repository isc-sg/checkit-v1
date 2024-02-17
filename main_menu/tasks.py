import math

from celery import shared_task
import sys
import cv2
import base64
import socket
import ipaddress
import time
from wurlitzer import pipes
import subprocess
import os
import mysql.connector
from bisect import bisect_left
import datetime
import configparser
# import itertools
import main_menu.a_eye
import main_menu.select_region
import pathlib
import json
from urllib.parse import urlparse
from celery.utils.log import get_task_logger
# import random
import cython
import main_menu.dris as dris
import skimage
import hashlib

from main_menu.dplin64py import DDProtCheck
from cryptography.fernet import Fernet, InvalidToken

from .models import ReferenceImage, LogImage, Camera, EngineState, Licensing
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.db import transaction


so_directory = os.path.abspath('/home/checkit/camera_checker/main_menu')
sys.path.append(so_directory)
logger = get_task_logger(__name__)

MY_SDSN = 10101  # !!!! change this value to be the value of your SDSN (demo = 10101)
MY_PRODCODE = "DEMO"  # !!!! change this value to be the value of the Product Code in the dongle

socket_timeout = 2
camera_details_dict = {}
CHECKIT_HOST = ""
HOST = ""
PORT = 0
network_interface = ""
log_alarms = False


def get_config():
    config = configparser.ConfigParser()
    config.read('/home/checkit/camera_checker/main_menu/config/config.cfg')
    global CHECKIT_HOST
    global HOST
    global PORT
    global network_interface
    global log_alarms

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
                logger.error("Please check config file for synergy host address")

        PORT = 0
        if config.has_option('DEFAULT', 'synergy_port',):
            try:
                PORT = config.getint('DEFAULT', 'synergy_port', fallback=0)
            except ValueError:
                logger.error("Please check config file for synergy port number")

        CHECKIT_HOST = config['DEFAULT']['checkit_host']
    except configparser.NoOptionError:
        logger.error("Unable to read config file")
        # exit(0)


# network_interface = "enp0s5"

# this dictionary should contain camera_id(database record id): {parameters: value}
# example camera 22 in DB is record id 66
# {66: {"camera_name": "Entry Camera", "camera_number": 1, "url": "rtsp://1.2.3.4/"},

def array_to_string(array):
    new_string = ""
    for element in array:
        new_string += chr(element)
    return new_string


def get_encrypted(password):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(password.encode())
    h_in_hex = h.hexdigest().upper()
    return h_in_hex


def check_adm_database(password):
    adm_db_config = {
        "host": "localhost",
        "user": "root",
        "password": password,
        "database": "adm"
    }

    try:
        adm_db = mysql.connector.connect(**adm_db_config)
    except mysql.connector.Error:
        try:
            adm_db_config = {
                "host": "localhost",
                "user": "root",
                "password": "",
                "database": "adm"
            }
            adm_db = mysql.connector.connect(**adm_db_config)

        except mysql.connector.Error as e:
            logger.error(f"Failed all attempts at accessing database  {e}")
    try:
        admin_cursor = adm_db.cursor()
        sql_statement = "SELECT * FROM adm ORDER BY id DESC LIMIT 1"
        admin_cursor.execute(sql_statement)
        result = admin_cursor.fetchone()
        if result:
            field_names = [i[0] for i in admin_cursor.description]

            current_transaction_count_index = field_names.index('tx_count')
            current_transaction_limit_index = field_names.index('tx_limit')
            current_end_date_index = field_names.index('end_date')
            current_camera_limit_index = field_names.index('camera_limit')
            current_license_key = field_names.index('license_key')

            current_transaction_count = result[current_transaction_count_index]
            current_transaction_limit = result[current_transaction_limit_index]
            current_end_date = result[current_end_date_index]
            current_camera_limit = result[current_camera_limit_index]
            current_license_key = result[current_license_key]
        else:
            current_transaction_count = 0
            current_transaction_limit = 0
            current_end_date = datetime.datetime.now().strftime("%Y-%m-%d")
            current_camera_limit = 0
            current_license_key = ""
        # TODO clean up long lines by making this list of variables a dictionary. Helps creating long lines.
        adm_db.close()

    except mysql.connector.Error as e:
        current_transaction_count = 0
        current_transaction_limit = 0
        current_end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_camera_limit = 0
        current_license_key = ""
        logger.error(f'Error connecting to admin: {e}')
    return (current_transaction_count, current_transaction_limit, current_end_date,
            current_camera_limit, current_license_key)


def get_license_details():
    global checkit_secret
    global key

    checkit_array = [52, 50, 52, 48, 54, 55, 49, 49, 57, 53, 54, 116, 105, 107, 99, 101, 104, 67]

    checkit_secret = array_to_string(checkit_array).encode()

    # key = b'Bu-VMdySIPreNgve8w_FU0Y-LHNvygKlHiwPlJNOr6M='

    key_array = [66, 117, 45, 86, 77, 100, 121, 83, 73, 80, 114, 101, 78, 103, 118, 101, 56, 119, 95, 70, 85, 48, 89,
                 45,
                 76, 72, 78, 118, 121, 103, 75, 108, 72, 105, 119, 80, 108, 74, 78, 79, 114, 54, 77, 61]

    key = array_to_string(key_array).encode()

    f = Fernet(key)
    machine_command_array = [47, 101, 116, 99, 47, 109, 97, 99, 104, 105, 110, 101, 45, 105, 100]
    machine_command = array_to_string(machine_command_array)
    # fd = open("/etc/machine-id", "r")
    # use ascii_to_string to obfuscate the command after compile
    fd = open(machine_command, "r")
    machine_uuid = fd.read()
    machine_uuid = machine_uuid.strip("\n")
    shell_command_array = [47, 98, 105, 110, 47, 100, 102]
    shell_command_string = array_to_string(shell_command_array)
    # shell_output = subprocess.check_output("/bin/df", shell=True)
    shell_output = subprocess.check_output(shell_command_string, shell=True)
    l1 = shell_output.decode('utf-8').split("\n")
    # command = "mount | sed -n 's|^/dev/\(.*\) on / .*|\\1|p'"
    command_array = [109, 111, 117, 110, 116, 32, 124, 32, 115, 101, 100, 32, 45, 110, 32, 39, 115, 124, 94, 47, 100,
                     101, 118, 47, 92, 40, 46, 42, 92, 41, 32, 111, 110, 32, 47, 32, 46, 42, 124, 92, 49, 124, 112, 39]

    command = array_to_string(command_array)
    root_dev = subprocess.check_output(command, shell=True).decode().strip("\n")

    # command = "/usr/bin/sudo /sbin/blkid | grep " + root_dev
    command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 47, 115, 98, 105,
                     110, 47, 98, 108, 107, 105, 100, 32, 124, 32, 103, 114, 101, 112, 32]

    command = array_to_string(command_array) + root_dev
    root_fs_uuid = subprocess.check_output(command, shell=True).decode().split(" ")[1].split("UUID=")[1].strip("\"")

    # # command = "/usr/bin/sudo dmidecode | grep -i uuid"
    # command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 100, 109, 105, 100,
    #                  101, 99, 111, 100, 101, 32, 124, 32, 103, 114, 101, 112, 32, 45, 105, 32, 117, 117, 105, 100]

    # new command to cater for servermax where multiple UUID are returned in dmidecode.  This will take the
    # line with a tab then UUID - other lines in server-max show \t\tService UUID although it's the same UUID
    # command = '/usr/bin/sudo dmidecode | grep -E "\tUUID"'

    command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 100, 109, 105, 100,
                     101, 99, 111, 100, 101, 32, 124, 32, 103, 114, 101, 112, 32, 45, 69, 32, 34, 9, 85, 85, 73, 68, 34]

    command = array_to_string(command_array)
    product_uuid = subprocess.check_output(command, shell=True).decode(). \
        strip("\n").strip("\t").split("UUID:")[1].strip(" ")

    finger_print = (root_fs_uuid + machine_uuid + product_uuid)
    fingerprint_encrypted = get_encrypted(finger_print)
    mysql_password = fingerprint_encrypted[10:42][::-1]
    current_transaction_count, current_transaction_limit, current_end_date, current_camera_limit, current_license_key = check_adm_database(mysql_password)

    # check adm DB if license details exist - if so load them.  Need to modify compare_images_v4 and process_list
    # with new logic to get password license details.

    license_dict = {"end_date": current_end_date,
                    "purchased_transactions": current_transaction_limit,
                    "purchased_cameras": current_camera_limit,
                    "license_key": current_license_key,
                    "machine_uuid": machine_uuid,
                    "root_fs_uuid": root_fs_uuid,
                    "product_uuid": product_uuid}
    encoded_string = f.encrypt(str(license_dict).encode())
    return machine_uuid, root_fs_uuid, product_uuid, encoded_string, mysql_password


machine_uuid, root_fs_uuid, product_uuid, encoded_string, mysql_password = get_license_details()


def ProtCheck():
    # create the DRIS and allocate the values we want to use
    mydris = dris.create()
    dris.set_function(mydris, dris.PROTECTION_CHECK)  # standard protection check
    dris.set_flags(mydris,0)  # no extra flags, but you may want to specify
                                   # some if you want to start a network user or decrement execs,...

    ret_code = DDProtCheck(mydris)

    if (ret_code != 0):
        dris.DisplayError(ret_code, dris.get_ext_err(mydris))
        return ret_code

    # later in your code you can check other values in the DRIS...
    if (dris.get_sdsn(mydris) != MY_SDSN):
        # print("Incorrect SDSN! Please modify your source code so that MY_SDSN is set to be your SDSN.")
        return "Incorrect Protection Serial Number!"

    if (dris.get_prodcode(mydris) != MY_PRODCODE):
        # print("Incorrect Product Code! Please modify your source code "
        #       "so that MY_PRODCODE is set to be the Product Code in the dongle.")
        return "Incorrect Protection Product Code!"

    # later on in your program you can check the return code again
    if (dris.get_ret_code(mydris) != 0):
        # print("Dinkey Dongle protection error")
        return "Protection Error"

    # print("It worked!")
    # logger.info("DONGLE WORKED")
    return ret_code


# ProtCheck()


def get_camera_details(list_of_lists):
    try:
        if not list_of_lists:
            return "Error - camera list does not contain any cameras"
        db_config_checkit = {
            "host": CHECKIT_HOST,
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        checkit_db = mysql.connector.connect(**db_config_checkit)
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute("SELECT * FROM main_menu_camera LIMIT 1")
        fields_result = checkit_cursor.fetchone()
        field_names = [i[0] for i in checkit_cursor.description]
        # logger.info(f"fieldnames {fields_result}")
        # merged_list = [item for sublist in list_of_lists for item in sublist]
        # merged_list_string = str(merged_list).replace("[", "").replace("]", "")
        list_as_string = ",".join(map(str, list_of_lists))
        list_as_string = "(" + list_as_string + ")"
        checkit_cursor.execute(f"SELECT * FROM main_menu_camera WHERE id IN {list_as_string}")
        checkit_result = checkit_cursor.fetchall()
        checkit_cursor.close()
        fields_dict = {}
        checkit_db.close()
        for result in checkit_result:
            for idx, field_name in enumerate(field_names):
                fields_dict[field_name] = result[idx]
            camera_details_dict[fields_dict['id']] = fields_dict
            fields_dict = {}
        checkit_db = mysql.connector.connect(**db_config_checkit)
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(f"SELECT camera_id, daysofweek_id FROM main_menu_camera_scheduled_days WHERE camera_id IN {list_as_string}")
        rows = checkit_cursor.fetchall()
        checkit_cursor.close()
        result_dict = {}
        for row in rows:
            camera_id, daysofweek_id = row
            if camera_id not in result_dict:
                result_dict[camera_id] = []
            result_dict[camera_id].append(daysofweek_id)
        for camera in list_of_lists:
            value = camera_details_dict[camera]
            try:
                value["daysofweek"] = result_dict[camera]
            except KeyError:
                value["daysofweek"] = []
            camera_details_dict[camera] = value
        checkit_db = mysql.connector.connect(**db_config_checkit)
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(f"SELECT camera_id, hoursinday_id FROM main_menu_camera_scheduled_hours WHERE camera_id IN {list_as_string}")
        rows = checkit_cursor.fetchall()
        checkit_cursor.close()
        result_dict = {}
        for row in rows:
            camera_id, hoursinday_id = row
            if hoursinday_id == 24:
                hoursinday_id = 0
            if camera_id not in result_dict:
                result_dict[camera_id] = []
            result_dict[camera_id].append(hoursinday_id)
        for camera in list_of_lists:
            value = camera_details_dict[camera]
            try:
                value["hoursinday"] = result_dict[camera]
            except KeyError:
                value["hoursinday"] = []
            camera_details_dict[camera] = value
        return camera_details_dict

    except mysql.connector.Error as err:
        if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("Invalid password on main database")
            return "Invalid password on main database"
            # consider not existing  ... this should exist with error code
        elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
            logger.error("Database not initialised")
            return "Checkit database not initialised"
        else:
            # print(err, "*",merged_list_string,"*")
            return err

    # try:
    #     password = mysql_password
    #     adm_db_config = {
    #         "host": CHECKIT_HOST,
    #         "user": "root",
    #         "password": password,
    #         "database": "adm"
    #     }
    #     adm_db = mysql.connector.connect(**adm_db_config)
    # except mysql.connector.Error as err:
    #     if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
    #         logger.error(f"Invalid password")
    #         return "Invalid password on admin database"
    #         # TODO - this exit doesn't close properly when run from start.py
    #     elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
    #         logger.error(f"Database not initialised")
    #         return "Admin database not initialised"


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
        url_port = 554
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        logger.error(f"Invalid IP address in {url}")
        ip_address = "Error"
    return ip_address, url_port, scheme


def check_uri(uri):
    ip_address, url_port, scheme = extract_ip_from_url(uri)

    try:
        ipaddress.ip_address(ip_address)

    except ValueError:
        # print((colored("Invalid IP address" + str(uri), 'red', attrs=['reverse', 'blink'])))
        logger.error(f"Invalid IP address {uri}")
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
            logger.error(f"Error in URL for camera url {url}")
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
                logger.error(f"Unable to join multicast group - {error_output}")
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
            logger.error(f"Unable to open session description file for {url}")
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
                logger.error(f"Error opening camera {url} - {err} ")

        if not cap.isOpened():
            try:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            except cv2.error as err:
                logger.error(f"Error opening camera {url} - {err}")
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



def close_capture_device(cap, multicast_address):
    cap.release()

    if multicast_address:
        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'del',
                             multicast_address + '/32', 'dev', network_interface])
        error_output = err.read()
        if error_output:
            logger.error(f"Unable to leave multicast group - {error_output}")


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


def send_alarms(list_of_cameras, camera_dict, run_number):
    # logger.info(f"Processing list of cameras {list_of_cameras} {run_number}")
    if HOST is None or PORT == 0:
        logger.error(f"Error in config - HOST = {HOST}, PORT = {PORT}")
        return

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(socket_timeout)
        s.connect((HOST, PORT))
        s.close()
    except socket.error as e:
        logger.error(f"Alarm Server Socket creation error: {e}")
        return


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

    # combined_list = list(itertools.chain.from_iterable(list_of_cameras))
    sql_statement = "SELECT url_id, creation_date, action, image, matching_score, focus_value, light_level, reference_image_id " \
                    "FROM main_menu_logimage " \
                    "WHERE action != 'Pass' AND url_id IN ({}) " \
                    "AND run_number = {}".format(','.join(map(str, list_of_cameras)), run_number)
    cursor = checkit_db.cursor()
    cursor.execute(sql_statement)
    f = cursor.fetchall()
    # print(len(f))
    # logger.info(f"log image results: {f}")
    for i in f:
        # logger.info(f"Processing log: {i}")

        url_id = i[0]
        creation_date = datetime.datetime.strftime(i[1], "%Y-%m-%d %H:%M:%S.%f")
        action = i[2]
        log_image: str = i[3]
        matching_score = i[4]
        focus_value = i[5]
        light_level = i[6]
        reference_image_id = i[7]
        # logger.info(f"reference_image_id : {reference_image_id}")

        # if reference_image_id == None:
        #     continue
        # sql_statement = "SELECT url, camera_number, camera_name, camera_location FROM main_menu_camera WHERE id = {}".format(url_id)
        # cursor.execute(sql_statement)
        # camera_details = cursor.fetchone()
        last_good_check = LogImage.objects.filter(url_id=url_id, action="Pass").last()
        # logger.info(f"last_good_check results: {last_good_check}")
        if last_good_check:
            last_good_check_date_time = last_good_check.creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            last_good_check_date_time = "NONE"
        # # print(camera_details)
        # camera_url = camera_details[0]
        # camera_number = camera_details[1]
        # camera_name = camera_details[2]
        # camera_location = camera_details[3]
        camera_url = camera_dict[url_id]['url']
        camera_number = camera_dict[url_id]['camera_number']
        camera_name = camera_dict[url_id]['camera_name']
        camera_location = camera_dict[url_id]['camera_location']
        if reference_image_id:
            sql_statement = "SELECT image, creation_date FROM main_menu_referenceimage WHERE id = " + str(reference_image_id)
            cursor.execute(sql_statement)
            reference_image = cursor.fetchone()
            reference_image_creation_date = reference_image[1].strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            reference_image = [""]
            reference_image_creation_date = ""
        additional_data = "lastGoodCheckDatetime=" + last_good_check_date_time + "&amp;referenceImageDatetime=" + reference_image_creation_date
        # logger.error(f"additional_data {additional_data} for {url_id})")

        image = "http://" + CHECKIT_HOST + "/media/" + log_image
        reference_image = "http://" + CHECKIT_HOST + "/media/" + reference_image[0]

        if reference_image_id:
            message = "Error detected on camera " + camera_url \
                      + "|with matching score result " + str(matching_score) \
                      + "|with focus value " + str(focus_value) \
                      + "|with light level " + str(light_level) \
                      + "|at location " + str(camera_location)
        else:
            message = "Capture Error on camera " + camera_url \
                      + "|at location " + str(camera_location)

        send_alarm = """<?xml version="1.0" encoding="UTF-8"?><Request command="sendAlarm" id="123">""" \
                     + "<message>" + "Camera Scene Validation Alarm" + "</message> " \
                     + "<text>" + message + "</text>" \
                     + "<cameraId>" + str(camera_number) + "</cameraId>" \
                     + "<param1>" + camera_location + "</param1>" \
                     + "<param2>" + str(camera_name) + "</param2>" \
                     + "<param3>" + str(camera_url) + "</param3>" \
                     + "<alarmType>" + "Checkit Alarm" + "</alarmType> " \
                     + "<delimiter>|</delimiter><sourceId>62501</sourceId>" \
                     + "<jpeg>" + image + "</jpeg>" \
                     + "<additionalJpeg>" + reference_image + "</additionalJpeg>" \
                     + "<hidden>" + "false" + "</hidden>" \
                     + "<additionalData>" + additional_data + "</additionalData>" \
                     + "<autoClose>true</autoClose></Request>""" + "\x00"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as e:
            logger.error(f"socket connect 2 {e}")
        try:
            s.connect((HOST, PORT))
            s.send(send_alarm.encode())
            # logger.info(send_alarm)
            reply = s.recv(8192).decode().rstrip("\x00")
            # print(reply)
            logger.info(f"Reply for Synergy {reply}")
        except socket.error as e:
            logger.error(f"Error sending to alarm server - {e}")

        # print(reply)


def sql_insert(table, fields, values):
    try:
        db_config_checkit = {
            "host": CHECKIT_HOST,
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
        logger.error(f"Database error during insert {e.msg} on table {table} with fields {fields}")
        print("Error message:", e.msg)


def sql_select(fields, table, where,  long_sql, fetch_all):

    try:
        db_config_checkit = {
            "host": CHECKIT_HOST,
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
        logger.error(f"Database error during select {e.msg}")
        print("Error message:", e.msg)


def sql_update(table, fields, where):

    sql_statement = "UPDATE " + table + " SET " + fields + where

    try:
        db_config_checkit = {
            "host": CHECKIT_HOST,
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
        logger.error(f"Database error during update {e.msg}")
        print("Error message:", e.msg)


def sql_update_adm(table, fields, where):

    sql_statement = "UPDATE " + table + " SET " + fields + where

    try:
        password = mysql_password
        adm_db_config = {
            "host": CHECKIT_HOST,
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
        logger.error(f"Database error during update on admin {e.msg}")
        print("Error message:", e.msg)


def increment_transaction_count():
    # table = "main_menu_licensing"
    # fields = "transaction_count =  transaction_count + 1"
    # where = " ORDER BY id DESC LIMIT 1"
    # sql_update(table, fields, where)

    # license_object = Licensing.objects.all().last()
    # license_object.transaction_count += 1
    # license_object.save()

    # table = "adm"
    # fields = "tx_count =  tx_count + 1"
    # where = " ORDER BY id DESC LIMIT 1"
    # sql_update_adm(table, fields, where)
    password = mysql_password
    adm_db_config = {
        "host": CHECKIT_HOST,
        "user": "root",
        "password": password,
        "database": "adm"
    }
    adm_db = mysql.connector.connect(**adm_db_config)
    try:
        adm_cursor = adm_db.cursor()
        sql_statement = "SELECT id FROM adm ORDER BY id DESC LIMIT 1"
        adm_cursor.execute(sql_statement)
        adm_id = adm_cursor.fetchone()[0]
        adm_cursor.execute("SELECT * FROM adm WHERE id = %s FOR UPDATE", (adm_id,))
        row = adm_cursor.fetchone()
        if row:
            sql_statment = "UPDATE adm SET tx_count = tx_count + 1 ORDER BY id DESC LIMIT 1"
            adm_cursor.execute(sql_statment)
            adm_db.commit()
            sql_statement = "SELECT tx_count FROM adm ORDER BY id DESC LIMIT 1"
            adm_cursor.execute(sql_statement)
            tx_count = adm_cursor.fetchone()[0]
            # print("TX COUNT", tx_count)
        else:
            logger.error("Unbale to update transaction count on admin")
            pass

    except mysql.connector.Error as e:
        logger.error("Error:", e)
        adm_db.rollback()

    finally:
        adm_cursor.close()
        adm_db.close()
        license_object = Licensing.objects.all().last()
        license_object.transaction_count = tx_count
        license_object.save()

    # with transaction.atomic():
    #     try:
    #         license_object = Licensing.objects.select_for_update().all().last()
    #     except Licensing.DoesNotExist:
    #         logger.error(f"Error updating transaction count")
    #         pass
    #     else:
    #         license_object.transaction_count += 1
    #         license_object.save()




def increment_engine_state_other_count(engines_state_id):
    # now = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
    # table = "main_menu_enginestate"
    # fields = f"number_others =  number_others + 1, state_timestamp = '{now}'"
    # where = f" WHERE id = {engines_state_id}"
    # sql_update(table, fields, where)
    with transaction.atomic():
        try:
            engine_object = EngineState.objects.select_for_update().get(id=engines_state_id)
        except EngineState.DoesNotExist:
            logger.error(f"Error saving engine state for run number {engines_state_id}")
            pass
        else:
            engine_object.number_others += 1
            engine_object.state_timestamp = timezone.now()
            engine_object.save()
    # engine_object = EngineState.objects.get(id=engines_state_id)
    # engine_object.number_others += 1
    # engine_object.state_timestamp = timezone.now()
    # engine_object.save()

def increment_engine_state_pass_count(engines_state_id):
    # now = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
    # table = "main_menu_enginestate"
    # fields = f"number_pass_images =  number_pass_images + 1, state_timestamp = '{now}'"
    # where = f" WHERE id = {engines_state_id}"
    # sql_update(table, fields, where)
    with transaction.atomic():
        try:
            engine_object = EngineState.objects.select_for_update().get(id=engines_state_id)
        except EngineState.DoesNotExist:
            logger.error(f"Error saving engine state for run number {engines_state_id}")
            pass
        else:
            engine_object.number_pass_images += 1
            engine_object.state_timestamp = timezone.now()
            engine_object.save()

    # engine_object = EngineState.objects.get(id=engines_state_id)
    # engine_object.number_pass_images += 1
    # engine_object.state_timestamp = timezone.now()
    # engine_object.save()

def increment_engine_state_failed_count(engines_state_id):
    # now = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
    # table = "main_menu_enginestate"
    # fields = f"number_failed_images =  number_failed_images + 1, state_timestamp = '{now}'"
    # where = f" WHERE id = {engines_state_id}"
    # sql_update(table, fields, where)
    with transaction.atomic():
        try:
            engine_object = EngineState.objects.select_for_update().get(id=engines_state_id)
        except EngineState.DoesNotExist:
            logger.error(f"Error saving engine state for run number {engines_state_id}")
            pass
        else:
            engine_object.number_failed_images += 1
            engine_object.state_timestamp = timezone.now()
            engine_object.save()
    # engine_object = EngineState.objects.get(id=engines_state_id)
    # engine_object.number_failed_images += 1
    # engine_object.state_timestamp = timezone.now()
    # engine_object.save()


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
            logger.error(f"Failed to get movement data {e}")

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

    # fv = cv2.Laplacian(frame_color, cv2.CV_64F).var()
    fv = skimage.measure.blur_effect(frame)
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

    # logger.debug(f"Match Score for full image is {full_ss}")
    # logger.debug(f"Match Score for regions is {scores_average}")
    # logger.debug(f"Focus value is {fv}")
    # logger.debug(f"All region scores are {region_scores}")

    return full_ss, fv, region_scores, frame_brightness


def no_base_image(camera, describe_data, user_name, engine_state_id):
    # connection = connection_pool.get_connection()
    # checkit_cursor = connection.cursor()
    logger.info(f"Capturing base image for {camera_details_dict[camera]['url']}")
    capture_device = open_capture_device(url=camera_details_dict[camera]['url'],
                                         multicast_address=camera_details_dict[camera]['multicast_address'],
                                         multicast_port=camera_details_dict[camera]['multicast_port'],
                                         describe_data=describe_data)

    if not capture_device.isOpened() or capture_device == "Error":
        logger.error(f"unable to open capture device {camera_details_dict[camera]['url']}")
        LogImage.objects.create(url_id=camera, region_scores={}, action="Capture Error",
                                creation_date=timezone.now(), user=user_name, run_number=engine_state_id)

        close_capture_device(capture_device, camera_details_dict[camera]['multicast_address'])
        return
    else:
        try:
            able_to_read, frame = capture_device.read()
            if not able_to_read:
                # raise NameError()
                logger.error(f"Unable to read from device for camera id {camera} / camera number {camera_details_dict[camera]['camera_number']}")

        except cv2.error as e:
            logger.error(f"cv2 error {e}")
        # except NameError:
        #     logging.error(f"Unable to read camera {camera_details_dict[camera]['camera_number']} - "
        #                   f"{camera_details_dict[camera]['camera_name']}")
        else:
            logger.debug(f"Able to capture base image on {camera_details_dict[camera]['camera_name']}")
            time_stamp = timezone.localtime()
            file_name = "/home/checkit/camera_checker/media/base_images/" + str(camera) + "/" + \
                        time_stamp.strftime('%H') + ".jpg"
            directory = "/home/checkit/camera_checker/media/base_images/" + str(camera)
            try:
                pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                os.system(f"sudo chmod 775 {directory}")

                if os.path.isfile(file_name):
                    os.remove(file_name)
                else:
                    try:
                        able_to_write = cv2.imwrite(file_name, frame)

                        os.system(f"sudo chmod 775 {directory}")

                        if not able_to_write:
                            logger.error(f"Unable to save reference image for id {camera} / "
                                         f" camera number {camera_details_dict[camera]['camera_number']}")
                            return
                        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        blur = cv2.blur(img_gray, (5, 5))
                        base_brightness = cv2.mean(blur)[0]
                        # focus_value = cv2.Laplacian(frame, cv2.CV_64F).var()
                        # focus_value = round(focus_value, 2)
                        fv = skimage.measure.blur_effect(img_gray)
                        fv = round(fv, 2)
                        # logger.info(f"Blur A {focus_value} Blur B {fv}")
                        sql_file_name = file_name.strip("/home/checkit/camera_checker/media/")
                        # table = "main_menu_referenceimage"
                        # fields = "(url_id, image, hour, light_level, creation_date, focus_value) VALUES (%s,%s,%s,%s,%s,%s)"
                        # values = (str(camera), sql_file_name,
                        #           time_stamp.strftime('%H'), base_brightness, timezone.now(), fv)
                        # sql_insert(table, fields, values)
                        # ReferenceImage.objects.create(url_id=camera, image=sql_file_name,
                        #                               hour=timezone.localtime().strftime('%H'),
                        #                               light_level=base_brightness,
                        #                               creation_date=timezone.now(), focus_value=fv)
                        ReferenceImage.objects.create(url_id=camera, image=sql_file_name,
                                                      hour=timezone.localtime().strftime('%H'),
                                                      light_level=base_brightness,
                                                      creation_date=timezone.now(), focus_value=fv, version=1)
                        # create log entry here with action as REFERENCE IMAGE
                    except:
                        logger.error(f"Unable to save reference image {file_name}")

            except Exception as error:
                logger.error(f"Unable to create base image directory/file {error}")
            close_capture_device(capture_device, camera_details_dict[camera]['multicast_address'])


def check(cameras, engine_state_id, user_name):
    current_time = timezone.localtime()
    current_hour = int(current_time.strftime('%H'))
    day_of_the_week = timezone.localtime().weekday() + 1

    logger.info(f"Starting check {cameras}")

    for camera in cameras:
        url = camera_details_dict[camera]['url']
        camera_number = camera_details_dict[camera]['camera_number']
        multicast_address = camera_details_dict[camera]['multicast_address']
        multicast_port = camera_details_dict[camera]['multicast_port']
        camera_username = camera_details_dict[camera]['camera_username']
        camera_password = camera_details_dict[camera]['camera_password']
        current_light_level = camera_details_dict[camera]['light_level_threshold']
        current_focus_value = camera_details_dict[camera]['focus_value_threshold']
        hoursinday = camera_details_dict[camera]["hoursinday"]
        daysofweek = camera_details_dict[camera]["daysofweek"]
        try:
            camera_object = Camera.objects.get(id=camera)
        except ObjectDoesNotExist:
            logger.error(f"Camera id {camera} does not exist")
            continue
        if int(current_hour) not in hoursinday:
            increment_engine_state_other_count(engine_state_id)
            continue
        if day_of_the_week not in daysofweek:
            increment_engine_state_other_count(engine_state_id)
            continue
        if camera_object.snooze:
            increment_engine_state_other_count(engine_state_id)
            continue

        message = f"Attempting connection to {url}\n"

        if camera_username and camera_password:
            url_parts = url.split("//")
            url = f"{url_parts[0]}//{camera_username}:{camera_password}@{url_parts[1]}"

        has_error = False
        ip_address, url_port, scheme = extract_ip_from_url(url)

        if scheme == "rtsp":
            options_response, has_error = options(url, ip_address, url_port, camera_username, camera_password)

            if not has_error:
                message = message + f"Connected to {url} - Unique ID {camera} - Camera Number {camera_number}"
            else:
                message = message + f"Error in OPTIONS for {url} {options_response}\n"

                LogImage.objects.create(url_id=camera, region_scores={}, action="Capture Error",
                                        creation_date=timezone.now(), user=user_name, run_number=engine_state_id)
                increment_transaction_count()
                increment_engine_state_other_count(engine_state_id)
                logger.error(message)
                continue

            describe_response, has_error = describe(url, ip_address, url_port, camera_username, camera_password)
            if has_error:
                message = message + f"Error in DESCRIBE for url {url} {describe_response}"

                LogImage.objects.create(url_id=camera, region_scores={}, action="Capture Error",
                                        creation_date=timezone.now(), user=user_name, run_number=engine_state_id)
                increment_transaction_count()
                increment_engine_state_other_count(engine_state_id)
                message = message + f"{describe_response}\n"

        if not has_error:
            capture_device = open_capture_device(url, multicast_address, multicast_port, describe_response)
            if capture_device != "Error":
                if not capture_device.isOpened():

                    LogImage.objects.create(url_id=camera, region_scores=[], action="Capture Error",
                                            creation_date=timezone.now(), user=user_name, run_number=engine_state_id)
                    increment_transaction_count()
                    increment_engine_state_other_count(engine_state_id)
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

                        fields = "hour"
                        table = "main_menu_referenceimage"
                        where = "WHERE url_id = " + "\"" + str(camera) + "\""
                        long_sql = None
                        captured_reference_hours = sql_select(fields, table, where, long_sql, fetch_all=True)
                        captured_reference_hours_integers = []
                        # logging.info(f"hours,{camera} {captured_reference_hours} ")
                        captured_reference_hours_integers = [int(item[0]) for item in captured_reference_hours]
                        captured_reference_hours_integers.sort()

                        if captured_reference_hours_integers:

                            # for i in range(0, len(captured_reference_hours)):
                            #     captured_reference_hours_integers.append(captured_reference_hours[i][0])
                            #     captured_reference_hours_integers[i] = int(captured_reference_hours_integers[i])


                            if current_hour not in captured_reference_hours_integers:
                                no_base_image(camera, describe_response, user_name, engine_state_id)
                                increment_transaction_count()
                                increment_engine_state_other_count(engine_state_id)
                                # continue

                            else:
                                # get the base image for the current camera at the current hour

                                # closest_hour = take_closest(captured_reference_hours_integers, current_hour)
                                # closest_hour = str(closest_hour).zfill(2)
                                fields = "image, id"
                                table = "main_menu_referenceimage"
                                where = "WHERE url_id = " + str(camera) + \
                                        " AND hour = " + str(current_hour)
                                long_sql = None
                                result = sql_select(fields, table, where, long_sql, fetch_all=False)
                                image = result[0]
                                reference_image_id = result[1]
                                base_image_location = "/home/checkit/camera_checker/media/" + image

                                # check that the image actually exists on the filesystem
                                if not os.path.isfile(base_image_location):
                                    logger.error(f'Base image missing for {base_image_location}')
                                    increment_transaction_count()
                                    continue

                                # read it
                                base_image = cv2.imread(base_image_location)

                                # save log image
                                time_stamp = timezone.now()
                                time_stamp_string = datetime.datetime.strftime(time_stamp, "%Y-%m-%d %H:%M:%S.%f")
                                directory = "/home/checkit/camera_checker/media/logs/" + str(time_stamp.year) + "/" + \
                                            str(time_stamp.month) + "/" + str(time_stamp.day)
                                log_image_file_name = directory + "/" + str(camera) + \
                                                      "-" + str(time_stamp.hour) + ":" + str(time_stamp.minute) + ":" + \
                                                      str(time_stamp.second) + ".jpg"
                                # attempt to save log file
                                try:
                                    pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                                    # os.chmod(directory, 0o775)
                                    os.system(f"sudo chmod 775 {directory}")

                                except OSError as error:
                                    logger.error(f"Error saving log file {error}")
                                    increment_transaction_count()
                                    continue

                                able_to_write = cv2.imwrite(log_image_file_name, image_frame)
                                # os.chmod(log_image_file_name, 0o664)
                                os.system(f"sudo chmod 775 {log_image_file_name}")
                                capture_dimensions = image_frame.shape[:2]
                                reference_dimensions = ()
                                status = "failed"

                                if not able_to_write:
                                    logger.error(f"Unable to write log image {log_image_file_name}")
                                    increment_transaction_count()
                                    continue
                                else:
                                    try:
                                        h, w, c = image_frame.shape
                                        # logger.info(f"Dimensions = {h} {w} {c}")
                                        if h < 720:
                                            scale = math.ceil(720 / h)
                                            logger.info(f"WARNING: Image size is below recommended minimum of 720p - "
                                                        f"images are being scaled up by factor of {scale} for analysis")
                                            image_frame = cv2.resize(image_frame, (h * scale, w * scale),
                                                                     interpolation=cv2.INTER_AREA)
                                            base_image = cv2.resize(base_image, (h * scale, w * scale),
                                                                    interpolation=cv2.INTER_AREA)
                                        image_base_grey = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
                                        image_frame_grey = cv2.cvtColor(image_frame, cv2.COLOR_BGR2GRAY)
                                        reference_dimensions = image_base_grey.shape[:2]
                                        capture_dimensions = image_frame_grey.shape[:2]
                                        status = "success"
                                    except cv2.error as err:
                                        logger.error(f"Error in converting image {err}")
                                        status = "failed"
                                        # need to test this return with cv2 error
                                        continue

                                    if reference_dimensions != capture_dimensions or status == "failed":
                                        logger.error(
                                            f"Image sizes don't match on camera number {camera}")
                                        # now = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
                                        # sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                                        # table = "main_menu_logimage"
                                        # fields = "(url_id, image, matching_score, region_scores, " \
                                        #          "current_matching_threshold, focus_value, " \
                                        #          "current_focus_value, light_level, current_light_level, action, " \
                                        #          "creation_date, user, run_number) " \
                                        #          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                        # values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error",
                                        #           now, user_name, engine_state_id)
                                        # sql_insert(table, fields, values)
                                        LogImage.objects.create(url_id=camera, region_scores={},
                                                                action="Image Size Error",
                                                                creation_date=timezone.now(), user=user_name,
                                                                run_number=engine_state_id)
                                        increment_transaction_count()
                                        increment_engine_state_other_count(engine_state_id)
                                        continue
                                    else:
                                        # this is the actual comparison section
                                        # check size of image - if image is too small then scale it up to support 720p
                                        # need to do this otherwise a_eye won't work properly.

                                        (matching_score,
                                         focus_value,
                                         region_scores,
                                         frame_brightness) = compare_images(image_base_grey,
                                                                            image_frame_grey,
                                                                            regions, base_image,
                                                                            image_frame)
                                        sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                                        # logger.info(f"Matching score {matching_score} cam ms {camera_details_dict[camera]['matching_threshold']}")
                                        if matching_score < camera_details_dict[camera]['matching_threshold']:
                                            action = "Failed"
                                            # logging.info("movement fail")
                                        else:
                                            action = "Pass"

                                        if action != "Failed":
                                            if focus_value > camera_details_dict[camera]['focus_value_threshold']:
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
                                                 "current_focus_value, current_light_level, user, run_number, reference_image_id) " \
                                                 "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
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
                                                  float(camera_details_dict[camera]['light_level_threshold']),
                                                  user_name,
                                                  engine_state_id,
                                                  reference_image_id
                                        )
                                        LogImage.objects.create(url_id=camera, image=sql_file_name,
                                                                matching_score=matching_score,
                                                                region_scores=json.dumps(region_scores),
                                                                current_matching_threshold=camera_details_dict[camera]['matching_threshold'],
                                                                light_level=frame_brightness,
                                                                focus_value=focus_value,
                                                                action=action,
                                                                creation_date=timezone.now(),
                                                                current_focus_value=camera_details_dict[camera]['focus_value_threshold'],
                                                                current_light_level=camera_details_dict[camera]['light_level_threshold'],
                                                                user=user_name,
                                                                run_number=engine_state_id,
                                                                reference_image_id=reference_image_id)
                                        # sql_insert(table, fields, values)

                                        table = "main_menu_camera"
                                        fields = "last_check_date = " + "\"" + time_stamp_string + "\""
                                        where = " WHERE id = " + "\"" + str(camera) + "\""
                                        # sql_update(table, fields, where)
                                        camera_object = Camera.objects.get(id=camera)
                                        camera_object.last_check_date = timezone.now()
                                        camera_object.save()

                                        increment_transaction_count()
                                        if action == "Pass":
                                            increment_engine_state_pass_count(engine_state_id)
                                        if action == "Failed":
                                            increment_engine_state_failed_count(engine_state_id)
                        else:
                            no_base_image(camera, describe_response, user_name, engine_state_id)
                            increment_transaction_count()
                            increment_engine_state_other_count(engine_state_id)
                            # image_frame = cv2.resize(image_frame,(960,540))
                            # cv2.imshow("image", image_frame)
                            # cv2.waitKey(50)
                            # message = message + f"Writting to /tmp/{camera_number}.jpg"
                            # cv2.imwrite(f"/tmp/{camera_number}.jpg", image_frame)
                    if not able_to_read:
                        # now = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
                        #
                        # table = "main_menu_logimage"
                        # fields = "(url_id, image, matching_score, region_scores, " \
                        #          "current_matching_threshold, focus_value, " \
                        #          "current_focus_value, light_level, current_light_level, action, " \
                        #          "creation_date, user, run_number) " \
                        #          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                        # values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error",
                        #           now, user_name, engine_state_id)
                        # sql_insert(table, fields, values)
                        LogImage.objects.create(url_id=camera, region_scores=[], action="Capture Error",
                                                creation_date=timezone.now(), user=user_name,
                                                run_number=engine_state_id)
                        increment_transaction_count()
                        increment_engine_state_other_count(engine_state_id)
                        # print("Error reading video frame")
                        message = message + "Error reading video frame\n"
                else:
                    # logging.error(f"Unable to open capture device {url}")
                    # now = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
                    #
                    # table = "main_menu_logimage"
                    # fields = "(url_id, image, matching_score, region_scores, " \
                    #          "current_matching_threshold, focus_value, " \
                    #          "current_focus_value, light_level, current_light_level, action, " \
                    #          "creation_date, user, run_number) " \
                    #          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    # values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error",
                    #           now, user_name, engine_state_id)
                    # sql_insert(table, fields, values)
                    LogImage.objects.create(url_id=camera, region_scores=[], action="Capture Error",
                                            creation_date=timezone.now(), user=user_name, run_number=engine_state_id)
                    increment_transaction_count()
                    increment_engine_state_other_count(engine_state_id)
                    # print("Error reading video frame")
                    message = message + f"Unable to open capture device {url}\n"
            else:
                # now = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
                # table = "main_menu_logimage"
                # fields = "(url_id, image, matching_score, region_scores, " \
                #          "current_matching_threshold, focus_value, " \
                #          "current_focus_value, light_level, current_light_level, action, " \
                #          "creation_date, user, run_number) " \
                #          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                # values = (str(camera), "", "0", "{}", "0", "0", "0", "0", "0", "Capture Error",
                #           now, user_name, engine_state_id)
                # sql_insert(table, fields, values)
                LogImage.objects.create(url_id=camera, region_scores=[], action="Capture Error",
                                        creation_date=timezone.now(), user=user_name, run_number=engine_state_id)
                increment_transaction_count()
                increment_engine_state_other_count(engine_state_id)
                # print("Error reading video frame")
                message = message + f"Unable to open capture device {url}\n"
        # message_queue.put(message)
        logger.info(message)


def check_license_ok():
    try:
        db_config_checkit = {
            "host": CHECKIT_HOST,
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        checkit_db = mysql.connector.connect(**db_config_checkit)
        sql_statement = "SELECT * FROM main_menu_licensing ORDER BY id DESC LIMIT 1"
        checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement)
        checkit_result = checkit_cursor.fetchone()
        checkit_cursor.close()
        checkit_db.close()
        field_names = [i[0] for i in checkit_cursor.description]
        fields_dict = {}
        for idx, field_name in enumerate(field_names):
            fields_dict[field_name] = checkit_result[idx]
        if (fields_dict['transaction_count'] > fields_dict['transaction_limit']
                or datetime.date.today() > fields_dict['end_date']):
            return False
        else:
            return True

    except mysql.connector.Error as e:
        logger.error(f"Database error during license check {e.msg}")


@shared_task()
def process_cameras(cameras, engine_state_id, user_name):
    get_config()
    # camera_object = Camera.objects.get(id=cameras[0])
    # logger.info(f"Processing camera {camera_object.camera_name}")
    if check_license_ok():
        # ret_code = ProtCheck()
        # logger.info(f"ret_code {ret_code}")
        # if ret_code != 0:
        #     return f"Licensing Error {ret_code}"
        # logger.info(f"{cameras}{engine_state_id}{user_name}")
        worker_id = process_cameras.request.hostname
        logger.info(f"Worker ID: {worker_id} Cameras {cameras}")
        camera_dict = get_camera_details(cameras)
        # logger.info(f"camera_dict {camera_dict}")
        if not isinstance(camera_details_dict, dict):
            logger.info(f'Error in camera details - {camera_dict}')
            sys.exit(1)

        check(cameras, engine_state_id, user_name)
        # logger.info(f"log_alarms {log_alarms}")

        logs = LogImage.objects.filter(run_number=engine_state_id)
        if logs:
            last_log_time = logs.last().creation_date
            engine_start_time = EngineState.objects.get(id=engine_state_id - 1).state_timestamp
            transaction_rate = math.floor(len(logs) / (last_log_time.timestamp() - engine_start_time.timestamp()))
        # logger.info(f"Transaction rate is {transaction_rate}")

            try:
                engine_object = EngineState.objects.all().last()
                engine_object.transaction_rate = transaction_rate
                engine_object.save()
            except EngineState.DoesNotExist:
                logger.error(f"Error updating transaction rate")

        if log_alarms:
            send_alarms(cameras, camera_dict, engine_state_id)

    else:
        logger.error(f"You license has either expired or exhausted the available transactions")

