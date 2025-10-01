import time

from Cython.Compiler.Errors import message
from celery.utils.log import get_task_logger
from celery import shared_task, chord, chain
import celery
import mysql.connector

import cv2
import os
import sys
import configparser
import datetime
from datetime import timedelta
import math
import socket
from cryptography.fernet import Fernet
import subprocess
import hashlib
import ipaddress
from urllib.parse import urlparse
import base64

from django.db.backends.mysql.base import version
from wurlitzer import pipes
import skimage
from skimage import color
from main_menu import select_region
from main_menu import a_eye
import json
import pathlib
import numpy as np
from scipy.signal import convolve2d
from scipy.ndimage import convolve
from scipy.stats import skew, kurtosis
import inspect
import requests
import glob
import ffmpeg
import struct
import urllib3
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .models import ReferenceImage, LogImage, Camera, EngineState, Licensing, SuggestedValues
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
# from django.db import transaction
from django.conf import settings
import main_menu.dris
from main_menu.dplin64py import DDProtCheck
from collections import defaultdict
import decimal
from math import isnan
from requests_toolbelt.multipart import decoder
import requests.auth
from django.contrib.admin.models import LogEntry
from datetime import timedelta
from itertools import islice



# camera_list = [10023, 10024, 10025, 10026, 10027, 10028, 10029, 10030,
#                10031, 10032, 10033, 10034, 10035, 10036, 10037, 10038]

__version__ = 2.11

logger = get_task_logger(__name__)


MY_SDSN = 13343             # !!!! change this value to be the value of your SDSN (demo = 10101)
MY_PRODCODE = "CHECKIT"		# !!!! change this value to be the value of the Product Code in the dongle


socket_timeout = 1
CHECKIT_HOST = ""
WEB_SERVER_PORT = None
HOST = ""
PORT = 0
network_interface = ""
log_alarms = False
mysql_password = None


def ProtCheck():
    # create the DRIS and allocate the values we want to use
    mydris = main_menu.dris.create()
    main_menu.dris.set_function(mydris, main_menu.dris.PROTECTION_CHECK)  # standard protection check
    main_menu.dris.set_flags(mydris,
                   main_menu.dris.START_NET_USER)  # no extra flags, but you may want to specify some if you want to start a network user or decrement execs,...

    ret_code = DDProtCheck(mydris)
    if ret_code == 423:
        time.sleep(5)
        ret_code = DDProtCheck(mydris)
    if (ret_code != 0):
        dongle_error = main_menu.dris.DisplayError(ret_code, main_menu.dris.get_ext_err(mydris))
        logger.error(f"Dongle Error {dongle_error} {ret_code}")
        return ret_code

    # later in your code you can check other values in the DRIS...
    if (main_menu.dris.get_sdsn(mydris) != MY_SDSN):
        logger.error("Incorrect SDSN! Please modify your source code so that MY_SDSN is set to be your SDSN.")
        return ret_code

    if (main_menu.dris.get_prodcode(mydris) != MY_PRODCODE):
        logger.error(
            "Incorrect Product Code! Please modify your source code so that MY_PRODCODE is set to be the Product Code in the dongle.")
        return ret_code

    # later on in your program you can check the return code again
    if (main_menu.dris.get_ret_code(mydris) != 0):
        logger.error("Dongle protection error")
        return ret_code

    # print("It worked!")
    # print(dris.get_dongle_number(mydris))
    main_menu.dris.set_function(mydris, main_menu.dris.PROTECTION_CHECK)
    main_menu.dris.set_flags(mydris, main_menu.dris.STOP_NET_USER)
    ret_code = DDProtCheck(mydris)
    return ret_code

@shared_task
def setup_task():
    # Perform some setup actions
    logger.info("Setup task running")
    ret_code = ProtCheck()
    # ret_code = 0
    if ret_code != 0:
        logger.error("LICENSE HARDWARE ERROR")
        return "License Hardware Failed"
    else:
        logger.info("LICENSE HARDWARE PASSED")
        return "Success"



@shared_task(name='main_menu.tasks.all_done', time_limit=333333, soft_time_limit=333333)
def all_done(previous_return_value, engine_state_id, camera_list):
    for return_value in previous_return_value:
        if return_value == "Success":
            continue
        else:
            logger.error(f"Camera check returned an error {return_value}")
    get_config()
    # This will run after all tasks in the chord are finished
    # logger.info(f"CAMERAS LIST {camera_list} {dummy} {engine_state_id}")
    flattened_list = [item for sublist in camera_list for item in sublist]
    cameras_details = Camera.objects.filter(id__in=flattened_list)
    logs = LogImage.objects.filter(run_number=engine_state_id)
    number_of_pass = logs.filter(action="Pass").count()
    number_of_fail = logs.filter(action="Triggered").count()
    number_of_skipped = logs.filter(action="Skipped").count()
    number_of_reference_capture = logs.filter(action="Reference Captured").count()
    number_of_capture_errors = logs.filter(action="Capture Error").count()
    number_of_image_size_errors = logs.filter(action="Image Size Error").count()
    number_of_others = (number_of_capture_errors + number_of_skipped +
                        number_of_reference_capture + number_of_image_size_errors)
    engine_start_time = EngineState.objects.get(id=engine_state_id - 1).state_timestamp
    engine_object = EngineState.objects.get(id=engine_state_id)


    if logs:
        last_log_time = logs.last().creation_date
        transaction_rate = math.floor(len(logs) / (last_log_time.timestamp() - engine_start_time.timestamp()))

        try:

            engine_object.transaction_rate = transaction_rate
            engine_object.number_pass_images = number_of_pass
            engine_object.number_failed_images = number_of_fail
            engine_object.number_others = number_of_others
            engine_object.state_timestamp = timezone.now()
            engine_object.save()

        except EngineState.DoesNotExist:
            logger.error(f"Error updating transaction rate")
    else:
        logger.info(f"No logs in this run {engine_state_id} ")

    if log_alarms:
        # hard code localhost as I don't expect using webserver off the main host
        # hard code for 3 scenarios only 8000, 80 and 443.
        web_server_type = check_web_server(CHECKIT_HOST, WEB_SERVER_PORT)
        if web_server_type != "Web server not running":

            if web_server_type.get("http"):
                web_server_type = "http"
            elif web_server_type.get("https"):
                web_server_type = "https"

        # logger.info(f"web_server_type {web_server_type}")
        if web_server_type in ["http", "https"]:
            send_alarms(cameras_details, engine_state_id, web_server_type)
        else:
            logger.error("Unable to connect to local server while sending alarm")
    if backup:
        # replicate the media directory
        command = ['rsync', '-aq', '--delete', 'camera_checker/media', f'checkit@{backup_server}:camera_checker']
        logger.info(command)
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("Media backup completed successfully")
        else:
            logger.error(f"Media backup failed with return code {result.returncode}")
            logger.error(f"Error output: {result.stderr}")

        # do mysqldump and transfer to back up server
        db_user = "checkit"
        db_password = "checkit"
        db_name = "checkit"
        backup_file = "backup.sql"

        # Define your rsync command with options
        with open(backup_file, 'w') as f:
            result = subprocess.run(
                ["mysqldump", "-u", db_user, f"-p{db_password}", db_name, "--no-tablespaces"],
                stdout=f,
                stderr=subprocess.PIPE
            )
        if result.returncode == 0:

            command = ['rsync', '-azq', 'backup.sql', f'checkit@{backup_server}:']
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode == 0:
                command = ['rm', 'backup.sql']
                result = subprocess.run(command, capture_output=True, text=True)
                logger.info("Database backup completed successfully")
            else:
                logger.error(f"Database backup failed with return code {result.returncode}")
                logger.error(f"Error output: {result.stderr}")
        else:
            logger.error(f"Database dump failed with return code {result.returncode}")
            logger.error(f"Error output: {result.stderr}")

    logger.info(f'All tasks are done! - TOTAL TIME {engine_object.state_timestamp - engine_start_time}')
    # logger.info(f'Results:{results}')


def check_web_server(site, port):
    if port:
        ip_portion_and_port = f"{site}:{port}"
    else:
        ip_portion_and_port = f"{site}"

    results = {}
    try:
        response = requests.get(f"https://{ip_portion_and_port}/", timeout=1, verify=False)
        results['https'] = (response.status_code, response.url)
        return results
    except requests.exceptions.RequestException as e:
        results['https'] = f'Error: {e}'
    try:
        response = requests.get(f"http://{ip_portion_and_port}/", timeout=1, verify=False)
        results['http'] = (response.status_code, response.url)
    except requests.exceptions.RequestException as e:
        results['http'] = f'Error: {e}'
        return results
    return "Web server not running"

def array_to_string(array):
    new_string = ""
    for element in array:
        new_string += chr(element)
    return new_string

def string_to_array(string):
    new_array = []
    for element in string:
        new_array.append(ord(element))
    return new_array

checkit_array = [52, 50, 52, 48, 54, 55, 49, 49, 57, 53, 54, 116, 105, 107, 99, 101, 104, 67]

checkit_secret = array_to_string(checkit_array).encode()

checkit_key_array = [66, 117, 45, 86, 77, 100, 121, 83, 73, 80, 114, 101, 78, 103,
                     118, 101, 56, 119, 95, 70, 85, 48, 89, 45, 76, 72, 78, 118, 121,
                     103, 75, 108, 72, 105, 119, 80, 108, 74, 78, 79, 114, 54, 77, 61]

checkit_key = array_to_string(checkit_key_array).encode()

def check_for_corruption_in_image(image, num_rows_to_check=100, tolerance=100):
    height, width = image.shape[:2]
    last_rows = image[height - num_rows_to_check:height, :]
    rows_above = image[height - 2 * num_rows_to_check:height - num_rows_to_check, :]

    # Calculate absolute difference between pixel values
    diff = np.abs(last_rows.astype(int) - rows_above.astype(int))

    return np.all(diff <= tolerance)

def custom_luminosity_scale(x):
    if x <= 0.2:
        # Map values in [0, 0.2] to [0, 0.5]
        scaled_value = 0.5 * x / 0.2
    else:
        # Map values in (0.2, 2] to (0.5, 1]
        scaled_value = 0.5 + 0.5 * (x - 0.2) / 1.8
    return scaled_value

def get_luminosity(frame):
    # Convert the tuple returned by cv2.split() to a list
    color = list(cv2.split(frame))

    # Apply luminance coefficients
    color[0] = np.uint8(color[0] * 0.299)
    color[1] = np.uint8(color[1] * 0.587)
    color[2] = np.uint8(color[2] * 0.114)

    lum = cv2.add(color[0], cv2.add(color[1], color[2]))

    summ = cv2.sumElems(lum)

    brightness = summ[0] / ((2 ** 8 - 1) * frame.shape[0] * frame.shape[1]) * 2  # percentage conversion factor
    return custom_luminosity_scale(brightness)

def format_datetime_with_milliseconds(dt):
    # Format datetime with milliseconds
    formatted_datetime = dt.strftime("%Y-%m-%d %H:%M:%S,")

    # Extract milliseconds (padded to 3 characters)
    milliseconds = str(dt.microsecond // 1000).zfill(3)

    # Combine formatted datetime and milliseconds
    formatted_datetime_with_ms = f"{formatted_datetime}{milliseconds}"

    return formatted_datetime_with_ms


def get_hash(password):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(password.encode())
    h_in_hex = h.hexdigest().upper()
    return h_in_hex


def check_adm_database(password):
    adm_db_config = {
        "host": CHECKIT_HOST,
        "user": "root",
        "password": password,
        "database": "adm"
    }
    try:
        adm_db = mysql.connector.connect(**adm_db_config)
    except mysql.connector.Error:
        try:
            adm_db_config = {
                "host": CHECKIT_HOST,
                "user": "root",
                "password": "",
                "database": "adm"
            }
            adm_db = mysql.connector.connect(**adm_db_config)

        except mysql.connector.Error as e:
            logger.error(f"Failed all attempts at accessing database  {e}")
            return None, None, None, None, None

    try:
        admin_cursor = adm_db.cursor(dictionary=True)
        sql_statement = "SELECT * FROM adm ORDER BY id DESC LIMIT 1"
        admin_cursor.execute(sql_statement)
        result = admin_cursor.fetchone()
        if not result:
            result = {'tx_count': 0, 'tx_limit': 0,
                      'end_date': timezone.now().strftime("%Y-%m-%d"), 'camera_limit': 0,
                      'license_key': ""}
            logger.error("System not licensed")
        adm_db.close()

    except mysql.connector.Error as e:
        result = {'tx_count': 0, 'tx_limit': 0,
                  'end_date': timezone.now().strftime("%Y-%m-%d"), 'camera_limit': 0,
                  'license_key': ""}
        logger.error(f'Error connecting to admin: {e}')
    return result


def get_license_details():
    f = Fernet(checkit_key)
    # there are currently 3 primary elements we gather in licensing. machine-id, root_fs_id and product_id/UUID
    # which is really just the UUID from dmidecode System Information
    # this approach mostly limits this to linux machines and needs reconsideration if moving to a different OS.

    # Below is the machine_id
    machine_command_array = [47, 101, 116, 99, 47, 109, 97, 99, 104, 105, 110, 101, 45, 105, 100]
    machine_file = array_to_string(machine_command_array)
    # fd = open("/etc/machine-id", "r")
    # use ascii_to_string to obfuscate the command after compile
    fd = open(machine_file, "r")
    _machine_uuid = fd.read()
    _machine_uuid = _machine_uuid.strip("\n")

    # Below is the code for getting the root_fs_id
    # firstly we need to know the device that root is mounted on
    # command = "mount | grep 'on / type'"
    command_array = [109, 111, 117, 110, 116, 32, 124, 32, 103, 114, 101, 112, 32, 39, 111, 110, 32, 47, 32, 116, 121,
                     112, 101, 39]
    command = array_to_string(command_array)
    command_output = subprocess.check_output(command, shell=True).decode()
    root_device = command_output.split()[0]

    # command = "/usr/bin/sudo /sbin/blkid | grep "
    command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 47, 115, 98, 105, 110, 47, 98,
                     108, 107, 105, 100, 32, 124, 32, 103, 114, 101, 112, 32]
    # convert the array to a string then add the root device to the end to complete the command.
    command = array_to_string(command_array) + root_device
    command_output = subprocess.check_output(command, shell=True).decode()
    _root_fs_uuid = command_output.split()[1].strip("UUID=").strip("\"")

    # shell_command_array = [47, 98, 105, 110, 47, 100, 102]
    # shell_command_string = array_to_string(shell_command_array)
    # # shell_output = subprocess.check_output("/bin/df", shell=True)
    # shell_output = subprocess.check_output(shell_command_string, shell=True)
    # # l1 = shell_output.decode('utf-8').split("\n")
    # # command = "mount | sed -n 's|^/dev/\(.*\) on / .*|\\1|p'"
    # command_array = [109, 111, 117, 110, 116, 32, 124, 32, 115, 101, 100, 32, 45, 110, 32, 39, 115, 124, 94, 47, 100,
    #                  101, 118, 47, 92, 40, 46, 42, 92, 41, 32, 111, 110, 32, 47, 32, 46, 42, 124, 92, 49, 124, 112, 39]
    #
    # command = array_to_string(command_array)
    # root_dev = subprocess.check_output(command, shell=True).decode().strip("\n")
    #
    # # command = "/usr/bin/sudo /sbin/blkid | grep " + root_dev
    # command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 47, 115, 98, 105,
    #                  110, 47, 98, 108, 107, 105, 100, 32, 124, 32, 103, 114, 101, 112, 32]
    #
    # command = array_to_string(command_array) + root_dev
    # _root_fs_uuid = subprocess.check_output(command, shell=True).decode().split(" ")[1].split("UUID=")[1].strip("\"")
    # # command = "/usr/bin/sudo dmidecode | grep -i uuid"
    # command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 100, 109, 105, 100,
    #                  101, 99, 111, 100, 101, 32, 124, 32, 103, 114, 101, 112, 32, 45, 105, 32, 117, 117, 105, 100]
    # new command to cater for servermax where multiple UUID are returned in dmidecode.  This will take the
    # line with a tab then UUID - other lines in server-max show \t\tService UUID although it's the same UUID
    # command = '/usr/bin/sudo dmidecode | grep -E "\tUUID"'
    # command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 100, 109, 105, 100,
    #                  101, 99, 111, 100, 101, 32, 124, 32, 103, 114, 101, 112, 32, 45, 69, 32, 34, 9, 85, 85, 73, 68, 34]
    #
    # command = array_to_string(command_array)
    # prod_uuid = subprocess.check_output(command, shell=True).decode(). \
    #     strip("\n").strip("\t").split("UUID:")[1].strip(" ")

    # Below is the code for getting the prod_uuid.  This is an improvement over earlier versions which
    # used grep to extract UUID. This version uses output directly from dmidecode to provide this value.
    # command = '/usr/bin/sudo dmidecode -s system-uuid'
    command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 100, 109, 105, 100, 101, 99, 111,
                     100, 101, 32, 45, 115, 32, 115, 121, 115, 116, 101, 109, 45, 117, 117, 105, 100]
    command = array_to_string(command_array)
    product_uuid = subprocess.check_output(command, shell=True).decode().strip("\n")

    finger_print = (_root_fs_uuid + _machine_uuid + product_uuid)
    fingerprint_hashed = get_hash(finger_print)
    db_password = fingerprint_hashed[10:42][::-1]
    adm_details = check_adm_database(db_password)
    current_transaction_limit = adm_details['tx_limit']
    current_end_date = adm_details['end_date']
    current_camera_limit = adm_details['camera_limit']
    current_license_key = adm_details['license_key']
    if not current_license_key:
        return None, None, None, None, None

    # check adm DB if license details exist - if so load them.  Need to modify compare_images_v4 and process_list
    # with new logic to get password license details.

    license_dict = {"end_date": current_end_date,
                    "purchased_transactions": current_transaction_limit,
                    "purchased_cameras": current_camera_limit,
                    "license_key": current_license_key,
                    "machine_uuid": _machine_uuid,
                    "root_fs_uuid": _root_fs_uuid,
                    "product_uuid": product_uuid,
                    "db_password": db_password}
    # string_encoded = f.encrypt(str(license_dict).encode())
    return license_dict


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


def get_config():
    config = configparser.ConfigParser()
    config.read('/home/checkit/camera_checker/main_menu/config/config.cfg')
    global CHECKIT_HOST
    global HOST
    global PORT
    global WEB_SERVER_PORT
    global network_interface
    global log_alarms
    global transaction_delay
    global freeze_threshold
    global backup
    global backup_server
    global log_retention_period_days

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

        WEB_SERVER_PORT = None
        try:
            WEB_SERVER_PORT = config.getint('DEFAULT', 'web_server_port', fallback=None)
        except ValueError:
            logger.error("Please check config file for web_server_port")

        CHECKIT_HOST = "localhost"
        if config.has_option('DEFAULT', 'checkit_host',):
            try:
                CHECKIT_HOST = config['DEFAULT']['checkit_host']
            except ValueError:
                logger.error("Please check config file for checkit_host")
        transaction_delay = 0

        try:
            transaction_delay = config.getint('DEFAULT', 'transaction_delay', fallback=0)
        except ValueError:
            logger.error("Please configure config file for transaction_delay")

        try:
            log_retention_period_days = config.getint('DEFAULT', 'log_retention_period_days', fallback=0)
        except ValueError:
            log_retention_period_days = 30

        try:
            freeze_threshold = config.getfloat('DEFAULT', 'freeze_threshold', fallback=0.99)
        except ValueError:
            logger.error("Please configure config file for freeze_threshold")

        try:
            backup = config.getboolean('DEFAULT', 'backup', fallback=False)
        except ValueError:
            logger.error("Please configure config file for backup")

        if backup:
            try:
                backup_server = config.get('DEFAULT', 'backup_server', fallback=False)
            except ValueError:
                logger.error("Please configure config file for backup_server")

    except configparser.NoOptionError:
        logger.error("Unable to read config file")


def get_camera_details(camera_list):

    if not camera_list:
        return None

    # use my_camera = cameras_object.filter(<field>=8623).first() to get a specific camera
    # given camera_number is unique it should return just one but use .first()
    # use my_camera.<field> to get specific value of field
    # in case field is many to many like scheduled hours
    # scheduled_hours = my_camera.scheduled_hours.all()
    # list(my_camera.scheduled_hours.values_list('hour_in_the_day', flat=True)) or
    # list(my_camera.scheduled_days.values_list('day_of_the_week', flat=True))

    flattened_list = [item for sublist in camera_list for item in sublist]

    return Camera.objects.filter(id__in=flattened_list)


def check_license_ok():
    global mysql_password

    license_dict = get_license_details()
    license_key = license_dict['license_key']
    machine_uuid = license_dict['machine_uuid']
    root_fs_uuid = license_dict['root_fs_uuid']
    product_uuid = license_dict['product_uuid']
    mysql_password = license_dict['db_password']
    purchased_transactions = license_dict['purchased_transactions']
    end_date = license_dict['end_date']
    purchased_cameras = license_dict['purchased_cameras']
    finger_print = (root_fs_uuid + machine_uuid + product_uuid)
    finger_print_hashed = get_hash(finger_print)
    # license_key_check_finger_print = get_hash(f"{purchased_transactions}{end_date}{finger_print_hashed}{purchased_cameras}")
    # it's important to use order_by as we will want to be sure we get the second last object later. Here we order by id
    # in descending order ( highest first ).
    license_objects = Licensing.objects.order_by('-id')

    # take first as we have reversed the order of the list - this represents the last and current license record
    license_object_first = license_objects.first()

    if license_objects.count() == 1:
        license_key_check = get_hash(
            f"{license_object_first.transaction_limit}"
            f"{license_object_first.end_date.strftime('%Y-%m-%d')}"
            f"{finger_print_hashed}"
            f"{purchased_cameras}")
        # print(license_object_first.end_date.strftime('%Y-%m-%d'))
        # logger.info(license_key_check)
        if license_key_check != license_object_first.license_key:
            logger.error(f"License corrupted")
            return False
    else:
        # the line below will get the second last object because the list is in descending order so 1 is the
        # second object and 0 is the first, therefore 1 is the second last object in this list.
        license_object_previous = license_objects[1]
        license_key_previous = license_object_previous.license_key

        license_check_licensing_info = get_hash(f"{license_object_first.transaction_limit}"
                                                f"{license_object_first.end_date.strftime('%Y-%m-%d')}"
                                                f"{license_key_previous}"
                                                f"{purchased_cameras}")
        if license_check_licensing_info != license_key:
            logger.error(f"License corrupted")
            return False

    if not (machine_uuid and root_fs_uuid and product_uuid):
        logger.error("Licensing error - no license details - unable to proceed")
        return False

    license_object = Licensing.objects.all().last()
    end_of_day_datetime_naive = datetime.datetime.combine(license_object.end_date, datetime.time.max)
    end_of_day_datetime = timezone.make_aware(end_of_day_datetime_naive, timezone.get_current_timezone())
    if license_object:
        if (license_object.transaction_count > license_object.transaction_limit or
           timezone.localtime() > end_of_day_datetime):
            return False
        else:
            return True


def send_alarms(cameras_details, run_number, web_server_type):

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

    alarm_logs = LogImage.objects.filter(run_number=run_number).exclude(action='Pass').exclude(action="Skipped").exclude(action="Reference Captured")
    for alarm in alarm_logs:
        url_id = alarm.url_id
        log_image = alarm.image
        matching_score = alarm.matching_score
        focus_value = alarm.focus_value
        light_level = alarm.light_level
        reference_image_id = alarm.reference_image_id
        current_matching_threshold = alarm.current_matching_threshold
        current_focus_threshold = alarm.current_focus_value
        current_light_level = alarm.current_light_level

        last_good_check = LogImage.objects.filter(url_id=url_id, action="Pass").last()

        if last_good_check:
            last_good_check_date_time = last_good_check.creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            last_good_check_date_time = "NONE"

        try:
            camera_url = cameras_details.get(id=url_id).url
        except ObjectDoesNotExist:
            continue
        camera_number = cameras_details.get(id=url_id).camera_number
        camera_name = cameras_details.get(id=url_id).camera_name
        camera_location = cameras_details.get(id=url_id).camera_location

        if reference_image_id:

            try:
                reference_image_object = ReferenceImage.objects.get(pk=reference_image_id)
            except ObjectDoesNotExist:
                logger.error(f"ERROR [send_alarm] reference image object does not exist {reference_image_id}")
                return
            reference_image = reference_image_object.image
            reference_image_creation_date = reference_image_object.creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            reference_image = [""]
            reference_image_creation_date = ""

        additional_data = ("lastGoodCheckDatetime=" + last_good_check_date_time +
                           "&amp;referenceImageDatetime=" + reference_image_creation_date +
                           "&amp;matchingThreshold=" + str(current_matching_threshold) +
                           "&amp;lightLevelThreshold=" + str(current_light_level) +
                           "&amp;focusLevelThreshold=" + str(current_focus_threshold) +
                           "&amp;run_number=" + str(run_number) )

        image = f"{web_server_type}://" + CHECKIT_HOST + "/media/" + log_image.name
        reference_image = f"{web_server_type}://" + CHECKIT_HOST + "/media/" + str(reference_image)

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
                     + "<autoClose>true</autoClose></Request>" + "\x00"

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, PORT))
            s.send(send_alarm.encode())
            reply = s.recv(8192).decode().rstrip("\x00")
            logger.info(f"Reply for Alarm Server {reply}")
        except socket.error as e:
            logger.error(f"Error sending to alarm server - {e}")


def increment_transaction_count(password):
    # password = mysql_password

    adm_db_config = {
        "host": CHECKIT_HOST,
        "user": "root",
        "password": password,
        "database": "adm"
    }
    try:
        adm_db = mysql.connector.connect(**adm_db_config)
    except mysql.connector.errors as error:
        logger.error(f"Error connection to database {error}")

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
            license_object = Licensing.objects.all().last()
            license_object.transaction_count = tx_count
            license_object.save()
        else:
            logger.error("Unable to update transaction count on admin")
            pass

    except mysql.connector.Error as e:
        logger.error("Error:", e)
        adm_db.rollback()

    finally:
        try:
            adm_cursor.close()
            adm_db.close()
        except mysql.connector.Error:
            pass


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
        response = f"Error connecting to device {error}"
        error_flag = True

    return response, error_flag


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

        response = f"Timed out connecting to device {url}"
        error_flag = True
    except socket.error as error:
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
            # logger.error(f"Error in URL for camera url {url}")
            return "Fail", f"Error in URL for camera url {url}\n"

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
                # logger.error(f"Unable to join multicast group - {error_output}")
                try:
                    os.remove(f"/tmp/{ip_address}.sdp")
                except OSError:
                    pass
                return "Fail", f"Unable to join multicast group - {error_output}\n"

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
                # logger.error(f"Error opening camera {url} - {err} ")
                return "Fail", f"Unable to open camera {url} using UDP - {err}\n"

        if not cap.isOpened():
            try:
                os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            except cv2.error as err:
                # logger.error(f"Error opening camera {url} - {err}")
                return "Fail", f"Unable to open camera {url} using TCP - {err}\n"
    else:
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'timeout;5000'
        logger.info(f"Opening in url {url} in TCP mode")

        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        # timeout_ms = 5000  # 5 seconds timeout
        # cap.set(cv2.CAP_PROP_OPENNI2_SYNC, timeout_ms)
        if not cap.isOpened():
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'timeout;5000'
            logger.info(f"Opening in url {url} UDP mode")
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            # timeout_ms = 5000  # 5 seconds timeout
            # cap.set(cv2.CAP_PROP_OPENNI2_SYNC, timeout_ms)
        if not cap.isOpened():
            return "Fail", f"Error opening non-multicast camera {url} using UDP or TCP\n"

    return "Success", cap


def close_capture_device(cap, multicast_address):
    if cap is None:
        return
    if isinstance(cap, str):
        pass
    else:
        cap.release()

    if multicast_address:
        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'del',
                             multicast_address + '/32', 'dev', network_interface])
        error_output = err.read()
        if error_output:
            logger.error(f"Unable to leave multicast group - {error_output}")


def log_capture_error(camera, user, engine_state_id, password):
    LogImage.objects.create(url_id=camera, region_scores=[], action="Capture Error",
                            creation_date=timezone.now(), user=user, run_number=engine_state_id)
    
    increment_transaction_count(password)


def estimate_noise(image):

    h, w = image.shape

    matrix = [[1, -2, 1],
              [-2, 4, -2],
              [1, -2, 1]]

    sigma = np.sum(np.sum(np.absolute(convolve2d(image, matrix))))
    sigma = sigma * math.sqrt(0.5 * math.pi) / (6 * (w-2) * (h-2))

    return sigma


def niqe(image):
    """
    Calculate the NIQE (Natural Image Quality Evaluator) metric for the given image.

    Args:
        image (ndarray): Input grayscale image.

    Returns:
        float: NIQE score.
    """
    # Define filter kernels
    image = np.array(image)
    sobel_filter = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
    lsf_filter = np.array([1, 4, 6, 4, 1]) / 16

    # Compute gradient magnitude using Sobel filter
    gradient_magnitude = np.sqrt(convolve(image, sobel_filter) ** 2 + convolve(image, sobel_filter.T) ** 2)

    # Compute local standard deviation of gradients
    lsg = convolve(gradient_magnitude, np.outer(lsf_filter, lsf_filter))
    lsg_mean = np.mean(lsg)

    # Compute local contrast
    lc = lsg / (lsg_mean + 1e-5)

    # Compute local structure
    ls = convolve(image, np.outer(lsf_filter, lsf_filter))

    # Compute skewness and kurtosis
    skewness = skew(ls.flatten())
    kurt = kurtosis(ls.flatten())

    # Compute NIQE score
    niqe_score = np.sqrt(np.mean(lc ** 2)) * (skewness ** 2 + kurt ** 2)

    return niqe_score


def compare_images(base, frame, regions):
    # time.sleep(1)
    h, w = frame.shape[:2]
    all_regions = []
    all_regions.extend(range(1, 65))
    region_scores = {}
    coordinates = select_region.get_coordinates(all_regions, h, w)
    scores = []

    noise_level = estimate_noise(frame)
    # niqe_level = niqe((frame/255.0))

    frame_equalised = cv2.equalizeHist(frame)
    frame_bilateral = cv2.bilateralFilter(frame_equalised, 9, 100, 100)
    base_equalised = cv2.equalizeHist(base)
    base_bilateral = cv2.bilateralFilter(base_equalised, 9, 100, 100)

    for idx, sub_region in enumerate(coordinates):
        (x, y), (qw, qh) = sub_region
        sub_img_frame = frame_bilateral[y:y + qh, x:x + qw]
        sub_img_base = base_bilateral[y:y + qh, x:x + qw]
        sub_region_matching_score = 0
        try:
            sub_region_matching_score = a_eye.movement(sub_img_base, sub_img_frame)
        except Exception as e:
            logger.error(f"Failed to get matching score for sub region {e}")

        region_scores[idx+1] = round(sub_region_matching_score, 2)

    for region in regions:
        sub_region_matching_score = region_scores[int(region)]
        scores.append(sub_region_matching_score)

    number_of_regions = len(regions)

    if number_of_regions < 64:
        sum_scores = sum(scores)
        matching_score = round(sum_scores / number_of_regions, 2)
    else:
        matching_score = round(a_eye.movement(base_bilateral, frame_bilateral), 2)

    try:
        # bw_image = color.rgb2gray(frame)
        focus_value = skimage.measure.blur_effect(frame)
        focus_value = round(1 - focus_value, 2)
    except Exception as e:
        logger.error(f'Error calculating focus value {e}')
        focus_value = 0
    if isnan(focus_value):
        logger.error(f'Error calculating focus value - returned NaN')
        focus_value = 0
    # blur = cv2.blur(frame, (5, 5))
    # light_level = cv2.mean(blur)[0]
    if matching_score < 0:
        matching_score = 0
    matching_score = float(matching_score)
    return {"matching score": matching_score, "focus value": focus_value,
            "region scores": region_scores, "noise_level": noise_level}


def compare_previous_image(current_image, camera_object):
    status = False
    # set current time so that it remains constant and doesn't change as we
    # call timezone.localtime().
    current_time = timezone.localtime()
    base_image_directory = (
        f"{settings.MEDIA_ROOT}/logs/"
        f"{current_time.strftime('%Y')}/"
        f"{current_time.strftime('%m')}/"
        f"{current_time.strftime('%d')}"
    )
    try:
        files = glob.glob(f"{base_image_directory}/{camera_object.id}-*.jpg")
    except OSError as e:
        logger.error(f"Unable to get log images for camera id{camera_object.id} "
                     f"camera number {camera_object.camera_number} - Error reported: "
                     f"{e}")
        return False
    try:
        last_file = sorted(files)[-1]
        last_file_image = cv2.imread(last_file)
        matching_score = a_eye.movement(current_image, last_file_image)
        if matching_score > freeze_threshold:
            status = True
    except IndexError:
        return status
    return status


def create_base_image(camera_object, capture_device, version, user, engine_state_id, password, image_frame=None):

    # time.sleep(1)
    message = ""
    dt = format_datetime_with_milliseconds(timezone.localtime())
    if image_frame is None or image_frame.size == 0:
        able_to_read, image_frame = capture_device.read()
        if able_to_read:
            corruption_in_image = check_for_corruption_in_image(image_frame)
            count = 0
            while corruption_in_image and count < 10:
                message = (f'[{dt}] INFO [create_base_image] - '
                           f'Error reading video frame from camera number {camera_object.camera_number} - '
                           f'camera id {camera_object.id}\n')
                able_to_read, image_frame = capture_device.read()
                if able_to_read:
                    corruption_in_image = check_for_corruption_in_image(image_frame)
                count += 1
    else:
        able_to_read = True

    # able_to_read, frame = capture_device.read()
    if not able_to_read:
        message = (f"[{dt}] INFO [create_base_image] - Unable to read from device for "
                   f"camera id {camera_object.id} / camera number {camera_object.camera_number}")
        return message

    logger.info(f"[{dt}] INFO [create_base_image] - Successfully captured reference image on"
                 f" camera number {camera_object.camera_number} - camera id {camera_object.id} ")

    base_image_dir = f"{settings.MEDIA_ROOT}/base_images"

    file_name = f"{base_image_dir}/{camera_object.id}/{str(version).zfill(4)}-{timezone.localtime().strftime('%H')}.jpg"
    try:
        pathlib.Path(base_image_dir+f"/{camera_object.id}").mkdir(parents=True, exist_ok=True)
        os.system(f"sudo chmod 775 {base_image_dir}/{camera_object.id}")
    except Exception as e:
        message = f"Unable to create or set permissions on reference image directory {e}"
        return message

    if os.path.isfile(file_name):
        os.remove(file_name)
    else:

        try:
            os.system(f"sudo chmod 775 {base_image_dir}/{camera_object.id}")
        except Exception as e:
            message = f"Unable to set permissions on {base_image_dir}/{camera_object.id} {e}"
            return message

        able_to_write = cv2.imwrite(file_name, image_frame)

        if not able_to_write:

            message = (f"Unable to save reference image for id {camera_object.id} / "
                       f" camera number {camera_object.camera_number}\n")
            message = message + f"{file_name} - {type(image_frame) - len(image_frame)}"
            return message

        try:

            # img_gray = cv2.cvtColor(image_frame, cv2.COLOR_BGR2GRAY)
            # blur = cv2.blur(img_gray, (5, 5))
            # base_brightness = cv2.mean(blur)
            try:
                base_brightness = get_luminosity(image_frame)
            except:
                logger.error("Error in base_brightness")
            # noise_level = estimate_noise(image_frame)
            # logger.info(f"Noise Level {noise_level}")
            try:
                bw_image = color.rgb2gray(image_frame)
                focus_value = skimage.measure.blur_effect(bw_image)
                focus_value = round(1 - focus_value, 2)
            except:
                logger.error(f'Error calculating focus value during reference image creation')
                focus_value = 0
            if isnan(focus_value):
                focus_value = 0
            # focus_value = skimage.measure.blur_effect(img_gray)
            # focus_value = round(1 - focus_value, 2)

            image_file_name = file_name.strip(f"{settings.MEDIA_ROOT}/")
            reference_image_id = None
            try:
                reference_image_id = ReferenceImage.objects.create(url_id=camera_object.id, image=image_file_name,
                                              hour=timezone.localtime().strftime('%H'),
                                              light_level=base_brightness,
                                              creation_date=timezone.now(),
                                              focus_value=focus_value,
                                              version=version)
            except:
                logger.error(f"Error in creating reference image for camera numer {camera_object.camera_number}")
            # create log entry here with action as REFERENCE IMAGE
            try:
                LogImage.objects.create(url_id=camera_object.id, image=None,
                                        matching_score=0,
                                        region_scores=json.dumps(None),
                                        current_matching_threshold=camera_object.matching_threshold,
                                        light_level=0,
                                        focus_value=0,
                                        action="Reference Captured",
                                        creation_date=timezone.localtime(),
                                        current_focus_value=camera_object.focus_value_threshold,
                                        current_light_level=camera_object.light_level_threshold,
                                        user=user,
                                        run_number=engine_state_id,
                                        reference_image_id=reference_image_id.id)
            except Exception as e:
                logger.error(f"Error in creating LogImage for camera number {camera_object.camera_number} - {e}")
            try:
                increment_transaction_count(password)
            except Exception as e:
                logger.error(f"Error in incrementing transaction count {e}")
        except Exception as e:
            message = f"Unable to save reference image {file_name} for camera id {camera_object.id} - error {e}"
            log_capture_error(camera_object.id, user, engine_state_id, password)
            # remove file created earlier as transaction failed.
            if os.path.isfile(file_name):
                os.remove(file_name)
            return message
    return "Capture succeeded"


def read_and_compare(capture_device, user, engine_state_id, camera_object, image_frame=None, password=None):
    multicast_address = camera_object.multicast_address
    camera = camera_object.id
    regions = camera_object.image_regions
    # logger.info(f"{camera} Start read at {round(time.time(), 2)}")
    task_timer = time.time()
    # message = (f"{camera} Start read at {round(time.time(), 2)}\n")
    message = ""
    function_name = read_and_compare.__name__
    dt = format_datetime_with_milliseconds(timezone.localtime())
    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'timeout;5000'

    if isinstance(image_frame,str):
        message = f"IMAGE FRAME ERROR {image_frame}\n"
    if image_frame is None or image_frame.size == 0:
        able_to_read, image_frame = capture_device.read()
        if able_to_read:
            corruption_in_image = check_for_corruption_in_image(image_frame)
            count = 0
            while corruption_in_image and count < 10:
                message = (f'[{dt}] INFO [read_and_compare] - '
                           f'Error reading video frame from camera number {camera_object.camera_number} - '
                           f'camera id {camera_object.id}\n')
                able_to_read, image_frame = capture_device.read()
                if able_to_read:
                    corruption_in_image = check_for_corruption_in_image(image_frame)
                count += 1

    else:
        able_to_read = True
    end_time = time.time()
    # logger.info(f"{camera} End read at {round(time.time(), 2)}")
    # frame = inspect.stack()[0]  # Get the frame record of the caller (1 level up)

    message = message + (f"[{dt}] INFO [read_and_compare] -"
               f" Completed low level read in {round(end_time - task_timer, 2)}\n")

    current_hour = str(timezone.localtime().hour).zfill(2)

    if not able_to_read:
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = (message + f"[{dt}] ERROR [read_and_compare] -" 
                   f" Error reading video frame for camera id {camera} camera number {camera_object.camera_number}\n")
        log_capture_error(camera, user, engine_state_id, password)

        # increment_transaction_count(password)
        close_capture_device(capture_device, multicast_address)
        return message

    if regions == '0' or regions == "[]":
        regions = []
        regions.extend(range(1, 65))
    else:
        regions = eval(regions)

    # alternative method to do the below function is to do the following
    # camera.referenceimage_set.all()
    # referenceimage_set is created by Django automatically.

    reference_image_objects = ReferenceImage.objects.filter(url_id=camera)
    # now lets make sure we get the last version of the reference image.
    # we do this by getting the last of reference_image_objects.
    # from there get the version number.
    last_version = camera_object.reference_image_version
    # if camera_object.trigger_new_reference_image:
    #     last_version += 1

    # elapsed_time = timezone.now() - camera_object.trigger_new_reference_image_date
    #
    # logger.info(
    #     f"[{timezone.now()}] DEBUG [read_and_compare] - trigger_new_reference_image: {camera_object.trigger_new_reference_image}")
    # logger.info(
    #     f"[{timezone.now()}] DEBUG [read_and_compare] - trigger_new_reference_image_date: {camera_object.trigger_new_reference_image_date}")
    # logger.info(f"[{timezone.now()}] DEBUG [read_and_compare] - last_version: {last_version}")
    # logger.info(f"[{timezone.now()}] DEBUG [read_and_compare] - elapsed_time: {elapsed_time}")

    if camera_object.trigger_new_reference_image:
        # logger.info("Entered zero")
        # if elapsed_time < timezone.timedelta(hours=24):
        last_version += 1

        if camera_object.trigger_copy_to_all:
            reference_image= None
            if not reference_image_objects.filter(hour=current_hour, version=last_version).exists():
                # logger.info("Entered first")
                message = (message + f"[{timezone.now()}] INFO [read_and_compare] -"
                                    f" Attempting capture of reference image\n")
                response = create_base_image(camera_object, capture_device, last_version,
                                            user, engine_state_id, password, image_frame)
                message = (message + f"[{timezone.now()}] INFO [read_and_compare] -"
                                    f" {response}\n")
                close_capture_device(capture_device, multicast_address)
            reference_image= reference_image_objects.filter(hour=current_hour, version=last_version).first()
            
            for hour in range(0,24):
                hour=str(hour).zfill(2)
                source_reference_image_object = reference_image
                image = source_reference_image_object.image
                version = str(source_reference_image_object.version).zfill(4)
                url_id = source_reference_image_object.url_id
                if reference_image_objects.filter(hour=hour, version=last_version).exists():
                    message = (message + f"[{timezone.now()}] INFO [read_and_compare] -"
                                    f"New version already exists for hour {hour}\n")
                    continue

                new_file_name = f"base_images/{url_id}/{version}-{hour}.jpg"
                try:
                    target_reference_image_object = ReferenceImage.objects.get(url_id = url_id, hour = hour, version = version)
                    if image != new_file_name:
                        result = subprocess.run(["cp", f"{settings.MEDIA_ROOT}/{image}", f"{settings.MEDIA_ROOT}/{new_file_name}"], capture_output=True, text=True)
                    if result.returncode != 0:
                        # handle error
                        # queryset = ReferenceImage.objects.all()
                        # table = ReferenceImageTable(queryset)
                        # table.paginate(page=request.GET.get("page", 1), per_page=24)
                        message = (message + f"[{timezone.now()}] ERROR [read_and_compare] -"
                                    f"Couldnt copy reference image {result.stderr}\n")
                except ObjectDoesNotExist:
                    # create here.
                    try:
                        ReferenceImage.objects.create(url=source_reference_image_object.url,
                                                    image=f"base_images/{url_id}/{version}-{hour}.jpg",
                                                    light_level=source_reference_image_object.light_level,
                                                    focus_value=source_reference_image_object.focus_value,
                                                    creation_date=timezone.now(),
                                                    version=int(version),
                                                    hour=hour
                                                    )
                        result = subprocess.run(["cp", f"{settings.MEDIA_ROOT}/{image}", f"{settings.MEDIA_ROOT}/{new_file_name}"], capture_output=True,
                                                text=True)
                        if result.returncode != 0:
                            # table = ReferenceImageTable(queryset)
                            # table.paginate(page=request.GET.get("page", 1), per_page=24)
                            message = (message + f"[{timezone.now()}] ERROR [read_and_compare] -"
                                    f"Couldnt copy reference image {result.stderr}\n")
                    except Exception as e:
                        # table = ReferenceImageTable(queryset)
                        # table.paginate(page=request.GET.get("page", 1), per_page=24)
                        message = (message + f"[{timezone.now()}] ERROR [read_and_compare] -"
                                    f"Error creating new reference image {result.stderr}\n")


            
            message = message + f"[{timezone.now()}] INFO [read_and_compare] - Copied all reference images after trigger and New reference image trigger reset\n"
            
            Camera.objects.filter(pk=camera_object.id).update(trigger_copy_to_all=False)
            Camera.objects.filter(pk=camera_object.id).update(trigger_new_reference_image=False)
            Camera.objects.filter(pk=camera_object.id).update(reference_image_version=last_version)

            # last_version -=1
            return message



        if not reference_image_objects.filter(hour=current_hour, version=last_version).exists():

            # logger.info("Entered first")
            message = (message + f"[{timezone.now()}] INFO [read_and_compare] -"
                                 f" Attempting capture of reference image\n")
            response = create_base_image(camera_object, capture_device, last_version,
                                         user, engine_state_id, password, image_frame)
            message = (message + f"[{timezone.now()}] INFO [read_and_compare] -"
                                 f" {response}\n")
            close_capture_device(capture_device, multicast_address)
            reference_image_id = None
            try:
                reference_image_id = ReferenceImage.objects.filter(url_id=camera, hour=current_hour, version=last_version)
            except ObjectDoesNotExist as e:
                message = (message + f"[{timezone.now()}] ERROR [read_and_compare] -"
                                 f" Unable to read newly created reference image {e}\n")
            # LogImage.objects.create(url_id=camera_object.id, image=None,
            #                         matching_score=0,
            #                         region_scores=json.dumps(None),
            #                         current_matching_threshold=camera_object.matching_threshold,
            #                         light_level=0,
            #                         focus_value=0,
            #                         action="Reference Captured",
            #                         creation_date=timezone.localtime(),
            #                         current_focus_value=camera_object.focus_value_threshold,
            #                         current_light_level=camera_object.light_level_threshold,
            #                         user=user,
            #                         run_number=engine_state_id,
            #                         reference_image_id=reference_image_id)
            return message
        elif reference_image_objects.filter(version=last_version).count() == 24:
            # logger.info("Entered second")
            # camera_object.trigger_new_reference_image = False
            # camera_object.reference_image_version = last_version + 1
            message = message + f"[{timezone.now()}] INFO [read_and_compare] - New reference image trigger reset\n"
            # logger.info(
            #     f"[{timezone.now()}] DEBUG [read_and_compare] - Resetting trigger_new_reference_image to False and updating reference_image_version to {camera_object.reference_image_version}")
            # camera_object.save()
            Camera.objects.filter(pk=camera_object.id).update(trigger_new_reference_image=False)
            Camera.objects.filter(pk=camera_object.id).update(reference_image_version=last_version)

    if not reference_image_objects.filter(hour=current_hour, version=last_version).exists():
        message = (message + f"[{dt}] INFO [read_and_compare] -"
                             f" Attempting capture of reference image for "
                             f"camera number {camera_object.camera_number} camera id {camera_object.id}\n")
        response = create_base_image(camera_object, capture_device, last_version,
                                     user, engine_state_id, password, image_frame)
        message = (message + f"[{dt}] INFO [read_and_compare] -"
                             f" {response}\n")
        close_capture_device(capture_device, multicast_address)
        return message
    # if trigger reference image lets do that
    # go back into create_base_image
    # then close capture device and return.
    # if camera_object.trigger_new_reference_image and (camera_object.trigger_new_reference_image_date)

    # this now becomes our version we append to file name and also add this to the get below.

    try:
        file_name = reference_image_objects.get(hour=current_hour, version=last_version).image
    except ObjectDoesNotExist:
        logger.error(f"filename object {camera} {current_hour} {last_version}")
        log_capture_error(camera, user, engine_state_id, password)
        return


    base_image_name = f"{settings.MEDIA_ROOT}/{file_name}"
    base_image = cv2.imread(base_image_name)
    if base_image is None:
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = (message + f"[{dt}] INFO [read_and_compare] -" 
                             f" Error reading reference image for "
                             f"camera id {camera} camera number {camera_object.camera_number}\n")
        log_capture_error(camera, user, engine_state_id, password)
        

        # increment_transaction_count(password)
        close_capture_device(capture_device, multicast_address)
        return message

    # check if image is low res
    h, w = image_frame.shape[:2]

    # keep original image for saving in case it's smaller than 720
    original_image_frame = image_frame
    if h < 720:
        scale = math.ceil(720 / h)
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = message + (f"[{dt}] WARNING [read_and_compare] -"
                             f" Image size is below recommended minimum of 720p - "
                             f"images are being scaled up by factor of {scale} for analysis "
                             f"for camera id {camera} camera number {camera_object.camera_number}\n")
        image_frame = cv2.resize(image_frame, (h * scale, w * scale),
                                 interpolation=cv2.INTER_AREA)
        base_image = cv2.resize(base_image, (h * scale, w * scale),
                                interpolation=cv2.INTER_AREA)

    # prepare images for checking - need grey scale
    try:
        image_base_grey = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
        image_frame_grey = cv2.cvtColor(image_frame, cv2.COLOR_BGR2GRAY)
        reference_dimensions = image_base_grey.shape[:2]
        capture_dimensions = image_frame_grey.shape[:2]
    except cv2.error as err:
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = message + (f"[{dt}] ERROR [read_and_compare] -"
                             f" Error in converting image {err}\n")
        

        increment_transaction_count(password)
        close_capture_device(capture_device, multicast_address)
        return message

    if reference_dimensions != capture_dimensions:
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = (message + f"[{dt}] ERROR [read_and_compare] -"
                             f"Image sizes don't match on camera number {camera}\n")
        LogImage.objects.create(url_id=camera, region_scores={},
                                action="Image Size Error",
                                creation_date=timezone.now(), user=user,
                                run_number=engine_state_id)
        

        increment_transaction_count(password)
        close_capture_device(capture_device, multicast_address)
        return message

    results_dict = compare_images(image_base_grey, image_frame_grey, regions)

    # Do the check here
    freeze_status = False
    if camera_object.freeze_check:
        freeze_status = compare_previous_image(image_frame, camera_object)

    matching_score = results_dict['matching score']
    focus_value = results_dict['focus value']
    region_scores = results_dict['region scores']
    if isnan(matching_score) or isnan(focus_value):
        log_capture_error(camera, user, engine_state_id, password)
        message = f"Error in value {matching_score} {focus_value} {region_scores}"
        return message

    # light_level = results_dict['light level']
    # use the function below to provide an alternative method for light level.
    try:
        light_level = get_luminosity(image_frame)
    except:
        logger.error(f"Error in light level for camera {camera_object.camera_number}")
        light_level = 0

    if isnan(light_level):
        light_level = 0
    current_time = timezone.localtime()
    base_image_directory = (
        f"{settings.MEDIA_ROOT}/logs/"
        f"{current_time.strftime('%Y')}/"
        f"{current_time.strftime('%m')}/"
        f"{current_time.strftime('%d')}"
    )
    log_image_file_name = (f"{base_image_directory}/"
                           f"{camera}-"
                           f"{timezone.localtime().strftime('%H')}:"
                           f"{timezone.localtime().strftime('%M')}:"
                           f"{timezone.localtime().strftime('%S')}.jpg")

    try:
        pathlib.Path(f"{base_image_directory}").mkdir(parents=True, exist_ok=True)
        os.system(f"sudo chmod 775 {base_image_directory}")
    except Exception as e:
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = (message + f"[{dt}] ERROR [read_and_compare] -"
                             f"Unable to create or set permissions on log directory {base_image_directory} - {e}")
        return message

    able_to_write = cv2.imwrite(log_image_file_name, original_image_frame)
    if not able_to_write:
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = (message + f"[{dt}] ERROR [read_and_compare] -"
                             f"Unable to write log file {log_image_file_name}")

        increment_transaction_count(password)
        close_capture_device(capture_device, multicast_address)
        return message

    focus_value = round(decimal.Decimal(str(focus_value)),2)
    light_level = round(decimal.Decimal(str(light_level)),2)

    if matching_score < camera_object.matching_threshold:
        action = "Triggered"
    elif focus_value < camera_object.focus_value_threshold:
        action = "Triggered"
    elif light_level < camera_object.light_level_threshold:
        action = "Triggered"
    else:
        action = "Pass"
    # if freeze_status:
      #  action = "Triggered"

    # code below allows for upper and lower range % on thresholds.
    # threshold_ranges = {
    #     'matching_score': camera_object.matching_threshold_range / 100.0 * camera_object.matching_threshold,
    #     'focus_value': camera_object.focus_value_threshold_range / 100.0 * camera_object.focus_value_threshold,
    #     'light_level': camera_object.light_level_threshold_range / 100.0 * camera_object.light_level_threshold
    # }
    #
    # if camera_object.matching_threshold_range == 0:
    #     matching_threshold_lower = camera_object.matching_threshold
    #     matching_threshold_upper = camera_object.matching_threshold
    # else:
    #     matching_threshold_lower = camera_object.matching_threshold - threshold_ranges['matching_score']
    #     matching_threshold_upper = camera_object.matching_threshold + threshold_ranges['matching_score']
    #
    # if camera_object.focus_value_threshold_range == 0:
    #     focus_value_threshold_lower = camera_object.focus_value_threshold
    #     focus_value_threshold_upper = camera_object.focus_value_threshold
    # else:
    #     focus_value_threshold_lower = camera_object.focus_value_threshold - threshold_ranges['focus_value']
    #     focus_value_threshold_upper = camera_object.focus_value_threshold + threshold_ranges['focus_value']
    #
    # if camera_object.light_level_threshold_range == 0:
    #     light_level_threshold_lower = camera_object.light_level_threshold
    #     light_level_threshold_upper = camera_object.light_level_threshold
    # else:
    #     light_level_threshold_lower = camera_object.light_level_threshold - threshold_ranges['light_level']
    #     light_level_threshold_upper = camera_object.light_level_threshold + threshold_ranges['light_level']
    #
    # if matching_score < matching_threshold_lower or matching_score > matching_threshold_upper:
    #     action = "Failed"
    # elif focus_value < focus_value_threshold_lower or focus_value > focus_value_threshold_upper:
    #     action = "Failed"
    # elif light_level < light_level_threshold_lower or light_level > light_level_threshold_upper:
    #     action = "Failed"
    # else:
    #     action = "Pass"
    try:
        LogImage.objects.create(url_id=camera,
                                image=log_image_file_name.strip(settings.MEDIA_ROOT),
                                matching_score=matching_score,
                                region_scores=json.dumps(region_scores),
                                current_matching_threshold=camera_object.matching_threshold,
                                light_level=light_level,
                                focus_value=focus_value,
                                freeze_status=freeze_status,
                                action=action,
                                creation_date=timezone.localtime(),
                                current_focus_value=camera_object.focus_value_threshold,
                                current_light_level=camera_object.light_level_threshold,
                                user=user,
                                run_number=engine_state_id,
                                reference_image_id=reference_image_objects.get(hour=current_hour, version=last_version).id)
    except:
        log_capture_error(camera, user, engine_state_id, password)
        message = message + f"Error saving log - {matching_score} {light_level} {focus_value}"
        return message
    increment_transaction_count(password)

    # camera_object = Camera.objects.get(id=camera)
    # camera_object.last_check_date = timezone.now()
    # camera_object.save()
    Camera.objects.filter(id=camera).update(last_check_date=timezone.now())
    close_capture_device(capture_device, multicast_address)
    return message


@shared_task(name='main_menu.tasks.check_the_camera', time_limit=333333, soft_time_limit=333333)
def check_the_camera(previous_task_return_value, camera_list, engine_state_id, user, password, force_check):
    get_config()

    # logger.info(f"Starting check {len(camera_list)} cameras [{camera_list[0]}..{camera_list[-1]}]")
    # logger.info(f"CAMERA LIST {camera_list}")
    if previous_task_return_value != "Success":
        return previous_task_return_value
    cameras_details = Camera.objects.filter(id__in=camera_list)
    if not cameras_details:
        logger.error(f'"Error - camera list does not contain any cameras" - {camera_list}')
        return "No cameras is list"
    psn_check = False
    for camera in camera_list:

        if transaction_delay > 0:
            logger.info(f"Sleeping {transaction_delay} seconds between transactions")
            time.sleep(transaction_delay)

        camera_object = Camera.objects.get(id=camera)


        start_timer = time.time()
        # camera_object = cameras_details.get(id=camera)
        url = camera_object.url
        camera_number = camera_object.camera_number
        multicast_address = camera_object.multicast_address
        multicast_port = camera_object.multicast_port
        camera_username = camera_object.camera_username
        camera_password = camera_object.camera_password
        hoursinday = list(camera_object.scheduled_hours.values_list('hour_in_the_day', flat=True))
        daysofweek = list(camera_object.scheduled_days.values_list('id', flat=True))
        psn_ipaddress = camera_object.psn_ip_address
        psn_recorded_port = camera_object.psn_recorded_port
        function_name = "check_the_camera"
        message = f"Starting check for camera id {camera} camera number {camera_object.camera_number}\n"

        if not force_check:

            if int(timezone.localtime().hour) not in hoursinday:
                dt = format_datetime_with_milliseconds(datetime.datetime.now())
                message = (message + f"[{dt}] INFO [check_the_camera] - "
                                     f"Not in scheduled hours "
                                     f"for camera id {camera} camera number {camera_object.camera_number}\n")
                logger.info(message)
                LogImage.objects.create(url_id=camera, image=None,
                                        matching_score=0,
                                        region_scores=json.dumps(None),
                                        current_matching_threshold=camera_object.matching_threshold,
                                        light_level=0,
                                        focus_value=0,
                                        action="Skipped",
                                        creation_date=timezone.now(),
                                        current_focus_value=camera_object.focus_value_threshold,
                                        current_light_level=camera_object.light_level_threshold,
                                        user=user,
                                        run_number=engine_state_id,
                                        reference_image_id=None)
                continue

            if timezone.localtime().weekday() + 1 not in daysofweek:
                dt = format_datetime_with_milliseconds(datetime.datetime.now())
                message = (message + f"[{dt}] INFO [check_the_camera] - "
                                     f"Not in scheduled days "
                                     f"for camera id {camera} camera number {camera_object.camera_number}\n")
                logger.info(message)
                LogImage.objects.create(url_id=camera, image=None,
                                        matching_score=0,
                                        region_scores=json.dumps(None),
                                        current_matching_threshold=camera_object.matching_threshold,
                                        light_level=0,
                                        focus_value=0,
                                        action="Skipped",
                                        creation_date=timezone.now(),
                                        current_focus_value=camera_object.focus_value_threshold,
                                        current_light_level=camera_object.light_level_threshold,
                                        user=user,
                                        run_number=engine_state_id,
                                        reference_image_id=None)
                continue

            if camera_object.snooze:
                dt = format_datetime_with_milliseconds(datetime.datetime.now())
                message = (message + f"[{dt}] INFO [check_the_camera] - "
                                     f"Camera set to snooze "
                                     f"for camera id {camera} camera number {camera_object.camera_number}\n")
                logger.info(message)
                LogImage.objects.create(url_id=camera, image=None,
                                        matching_score=0,
                                        region_scores=json.dumps(None),
                                        current_matching_threshold=camera_object.matching_threshold,
                                        light_level=0,
                                        focus_value=0,
                                        action="Skipped",
                                        creation_date=timezone.now(),
                                        current_focus_value=camera_object.focus_value_threshold,
                                        current_light_level=camera_object.light_level_threshold,
                                        user=user,
                                        run_number=engine_state_id,
                                        reference_image_id=None)
                continue

        psn_check = False

        if camera_object.psn_ip_address and not camera_object.psn_api_method:
            # mount the fs
            psn_recorded_port = camera_object.psn_recorded_port
            os.makedirs(name=f"/tmp/mount_points/{camera_object.psn_ip_address}", exist_ok=True)
            path = f"/tmp/mount_points/{camera_object.psn_ip_address}/recorded_video_data/{psn_recorded_port}"
            date_time_path = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d/%H/")
            curr_path = f"{path}/{date_time_path}"
            if os.path.isdir(curr_path):
                psn_check = True
            else:
                os.system(f'sudo mount -t cifs -o username={camera_object.psn_user_name},'
                          f'password={camera_object.psn_password} //{camera_object.psn_ip_address}/F$ /tmp/mount_points/{camera_object.psn_ip_address}/')
                if os.path.isdir(curr_path):
                    psn_check = True
                else:
                    logger.error(f"Unable to mount video storage for camera number {camera_object.camera_number}")
                    log_capture_error(camera, user, engine_state_id, password)
                    continue

        if camera_object.psn_api_method and camera_object.psn_ip_address:
            psn_check = True

        if psn_check and not camera_object.psn_api_method:
            # PSN's run on UTC time


            dt = format_datetime_with_milliseconds(timezone.localtime())
            path = f"/tmp/mount_points/{camera_object.psn_ip_address}/recorded_video_data/{psn_recorded_port}"
            date_time_path = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d/%H/")
            curr_path = f"{path}/{date_time_path}"
            if not os.path.isdir(curr_path):
                logger.error(f"Video storage path does not exist {curr_path}")
                log_capture_error(camera, user, engine_state_id, password)
                continue


            pattern = os.path.join(curr_path, '*_1.synav')
            dir_files = glob.glob(pattern)
            # logger.info(f"dir_files {dir_files[-1]}")
            if not dir_files:
                logger.info(f"ERROR NOT ABLE TO FIND PSN FILE")
                message = (message + f"[{dt}] ERROR [check_the_camera] -"
                                     f" Error reading video frame for camera id {camera} "
                                     f"camera number {camera_object.camera_number}\n")
                log_capture_error(camera, user, engine_state_id, password)
                logger.info(message)
                continue
            # logger.info(psn_recorded_port)
            # logger.info(dir_files)
            # need to do check for current hour and get that file.
            last_file_in_list = dir_files[-1]
            with open(last_file_in_list, "rb") as f:
                file_data = f.read()
            image_frame, status = read_from_file(file_data)
            if status != "Success":
                log_capture_error(camera, user, engine_state_id, password)
                continue
            capture_device = None
            message = str(message) + str(read_and_compare(capture_device, user, engine_state_id, camera_object, image_frame, password))
            logger.info(message)

            continue

        if psn_check and camera_object.psn_api_method:
            # currently hard coded but will change in future
            basic = requests.auth.HTTPBasicAuth('user', 'pass')
            # Get the current time in UTC
            current_time = datetime.datetime.now(datetime.timezone.utc)

            # Subtract one minute
            two_minute_prior = current_time - timedelta(minutes=2)

            # Format the time in the desired ISO 8601 format with 'Z'
            formatted_time = two_minute_prior.strftime("%Y-%m-%dT%H:%M:%SZ")
            # read only the "I" frame hence frameTypes=I as we don't need P frames

            psn_api_url = (f"https://{camera_object.psn_ip_address}:2242/services/v1/synav?streamID=" +
                           f"{camera_object.psn_recorded_port}&frameTypes=I&time={formatted_time}")
            try:
                response = requests.get(psn_api_url, auth=basic, verify=False)
            except requests.exceptions.ConnectionError as e:
                log_capture_error(camera_object, user, engine_state_id, password)
                # increment_transaction_count(password)
                message = f"Request to read from Video Server failed with error: {e}"
                logger.error(message)
                continue
            if response.status_code != 200:
                log_capture_error(camera, user, engine_state_id, password)
                # increment_transaction_count(password)
                message = message + (f"Request to read from Video Server failed with status code: "
                                     f"{response.status_code} - {response.content}")
                logger.error(message)

                continue
            status = None
            try:
                first_part = decoder.MultipartDecoder(response.content, response.headers['Content-Type']).parts[0]
                file_data = first_part.content
                image_frame, status = read_from_file(file_data)
            except ValueError as e:
                logger.error(f"ValueError during video request decode: {e}")
            except TypeError as e:
                logger.error(f"TypeError during video request decode: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred during video request decode: {e}")

            if status != "Success":
                log_capture_error(camera, user, engine_state_id, password)
                continue
            capture_device = None
            message = str(message) + str(
                read_and_compare(capture_device, user, engine_state_id, camera_object, image_frame, password))
            logger.info(message)

            continue

        # if user has entered a username and password set in the database then ensure that we use these
        # when we connect via the url. Add username and password to URL.

        if camera_username and camera_password:
            url_parts = url.split("//")
            url = f"{url_parts[0]}//{camera_username}:{camera_password}@{url_parts[1]}"

        ip_address, url_port, scheme = extract_ip_from_url(url)

        if ip_address == "Error":
            dt = format_datetime_with_milliseconds(datetime.datetime.now())
            message = (f"[{dt}] ERROR [check_the_camera] - "
                       f"Error in IP address for camera "
                       f"{camera_object.camera_name} {camera_number} {camera_object.id}\n")
            log_capture_error(camera, user, engine_state_id, password)


            # increment_transaction_count(password)
            logger.error(message)
            continue

        if scheme not in [
            "http",
            "https",
            "rtsp",
            "rtsps",
            "rtmp",
            "rtmps",
            "hls",
            "dash",
            "ftp",
            "smb",
            "udp",
            "tcp",
            "sftp"
        ]:
            logger.error(f"Unsupported URL scheme {scheme} "
                         f"for camera id {camera} camera number {camera_object.camera_number}\n")
            continue


        if scheme in ["rtsp", "rtsps"]:
            task_timer = time.time()
            options_response, has_error = options(url, ip_address, url_port, camera_username, camera_password)
            end_timer = time.time()
            # frame = inspect.stack()[0]  # Get the frame record of the caller (1 level up)
            # function_name = frame.function
            dt = format_datetime_with_milliseconds(datetime.datetime.now())
            message = message + (f"[{dt}] INFO [check_the_camera] -"
                                 f" Completed OPTIONS in {round(end_timer - task_timer, 2)} seconds\n")
            if has_error:
                end_timer = time.time()
                message = (f"[{dt}] ERROR [check_the_camera] - "
                           f"Error in OPTIONS for {url} {options_response} "
                           f"total time {round(end_timer - start_timer, 2)} seconds\n")
                log_capture_error(camera, user, engine_state_id, password)
                

                # increment_transaction_count(password)
                logger.error(message)
                continue
            task_timer = time.time()
            describe_response, has_error = describe(url, ip_address, url_port, camera_username, camera_password)
            end_timer = time.time()
            dt = format_datetime_with_milliseconds(datetime.datetime.now())
            message = message + (f"[{dt}] INFO [check_the_camera] - "
                                 f"Completed DESCRIBE in {round(end_timer - task_timer, 2)} seconds\n")

            if has_error:
                end_timer = time.time()
                message = (f"[{dt}] ERROR [check_the_camera] - "
                           f"Error in DESCRIBE for url {url} {describe_response} "
                           f"total time {round(end_timer - start_timer, 2)} seconds\n")
                log_capture_error(camera, user, engine_state_id, password)
                

                # increment_transaction_count(password)
                logger.error(message)
                continue

            status, capture_device = open_capture_device(url, multicast_address, multicast_port, describe_response)

            if status == "Fail" or not capture_device.isOpened():
                # code below is ugly - capture_device holds the error message in case it does not open
                message = f"{capture_device}"
                log_capture_error(camera, user, engine_state_id, password)
                

                # increment_transaction_count(password)
                close_capture_device(capture_device, multicast_address)
                logger.error(message)
                continue

            task_timer = time.time()
            message = message + (read_and_compare(capture_device, user, engine_state_id,
                                                  camera_object, None, password))
            end_timer = time.time()
            dt = format_datetime_with_milliseconds(datetime.datetime.now())
            message = message + (f"[{dt}] INFO [check_the_camera] - "
                                 f"Read and compare completed in {round(end_timer - task_timer, 2)} seconds\n")
        else:
            # this should be simple imread rather than open / describe etc.
            if camera_object.multicast_address:
                dt = format_datetime_with_milliseconds(datetime.datetime.now())
                message = (message + f"[{dt}] ERROR [check_the_camera] - "
                                     f"{scheme} over multicast is currently not supported\n")
                logger.error(message)
                continue
            capture_device = cv2.VideoCapture(camera_object.url)
            if not capture_device.isOpened():
                count = 0
                while count < 2:
                    capture_device = cv2.VideoCapture(camera_object.url)
                    if capture_device.isOpened():
                        break
                    count += 1
            if capture_device.isOpened():
                task_timer = time.time()
                message = message + (read_and_compare(capture_device, user, engine_state_id, camera_object, password))
                end_timer = time.time()
                dt = format_datetime_with_milliseconds(datetime.datetime.now())
                message = message + (f"[{dt}] INFO [check_the_camera] - "
                                     f"Completed read for camera id {camera} camera number {camera_object.camera_number} "
                                     f"in {round(end_timer - task_timer, 2)} seconds\n")
            else:
                end_timer = time.time()
                dt = format_datetime_with_milliseconds(datetime.datetime.now())
                message = (f"[{dt}] ERROR [check_the_camera] - "
                           f"Unable to open capture device {url} "
                           f"total time {round(end_timer - start_timer,2)} seconds\n")
                log_capture_error(camera, user, engine_state_id, password)
                

                # increment_transaction_count(password)
                close_capture_device(capture_device, multicast_address)
                logger.error(message)
                continue

        end_timer = time.time()
        dt = format_datetime_with_milliseconds(datetime.datetime.now())
        message = (message + f"[{dt}] INFO [check_the_camera] - "
                             f"Check complete - total time {round(end_timer - start_timer, 2)} seconds\n ")
        logger.info(message)

    # unmount here
    if psn_check and not camera_object.psn_api_method:
        os.system(f"umount -l /tmp/mount_points/{camera_object.psn_ip_address}/")

    return "Success"


@shared_task(name='main_menu.tasks.process_cameras')
def process_cameras(camera_list, engine_state_id, user_name, force_check=False):
    get_config()

    if check_license_ok():
        # ret_code = ProtCheck()
        # logger.info(f"ret_code {ret_code}")
        # if ret_code != 0:
        #     return f"Licensing Error {ret_code}"
        # logger.info(f"{cameras}{engine_state_id}{user_name}")
        # initial_setup = setup_task.s()
        # logger.info(f"initial setup {type(initial_setup)}")
        # psn_check = False
        worker_id = process_cameras.request.hostname
        logger.info(f"Worker ID: {worker_id} Cameras: {camera_list} Force Check: {force_check}")

        # cameras_details = get_camera_details(camera_list)
        # if not cameras_details:
        #     logger.error(f'"Error - camera list does not contain any cameras" - {camera_list}')
        #     sys.exit(1)
        # camera_object = Camera.objects.get(id=camera_list[0])
        # if camera_object.psn_ip_address:
        #     # mount the fs
        #     os.makedirs(name=f"/tmp/mount_points/{camera_object.psn_ip_address}", exist_ok=True )
        #     # os.system(f'sudo mount -t cifs -o username={camera_object.psn_user_name},'
        #     #           f'password={camera_object.psn_password} //{camera_object.psn_ip_address}/F$ /mnt/share')
        #     if os.path.isdir(f"/tmp/mount_points/{camera_object.psn_ip_address}/recorded_video_data"):
        #         psn_check = True
        # check_the_camera(camera_list, cameras_details, engine_state_id, user_name, psn_check)
        # [[ 125,146] [144, 156, 167]]
        header = [check_the_camera.s(data, engine_state_id,
                                     user_name, mysql_password, force_check) for data in camera_list]
        # logger.info(f"HEADER {type(header)} {header}")
        callback = all_done.s(engine_state_id, camera_list)
        # logger.info(f"CALLBACK {type(callback)} {callback}")

        main_tasks_chord = chord(header, callback)
        logger.info(f"main task chord {type(main_tasks_chord)}")

        # Create a chain to run the setup task first and then the chord of main tasks
        # logger.info(f"setup {type(setup_task.s())}, main {type(main_tasks_chord)}")
        workflow = chain(setup_task.s(), main_tasks_chord)

        # Execute the workflow
        workflow.apply_async()
    else:
        logger.error(f"Licensing error - please contact your software vendor for assistance")


# @shared_task
# def run_workflow(data_list):
#     # Create a chain that first runs the setup_task
#     initial_setup = setup_task.s()
#
#     # Create the main tasks as a chord
#     main_tasks = [process_cameras.s(data) for data in data_list]
#     main_tasks_chord = chord(main_tasks)(all_done.s())
#
#     # Create a chain to run the setup task first and then the chord of main tasks
#     workflow = chain(initial_setup, main_tasks_chord)
#
#     # Execute the workflow
#     workflow()

@shared_task(name='main_menu.tasks.do_nothing')
def do_nothing():
        pass


@shared_task(name='main_menu.tasks.start_find_best_regions')
def start_find_best_regions(camera_list):
    #
    # worker_id = start_find_best_regions.request.hostname
    # logger.info(f"Worker ID: {worker_id} Cameras: {camera_list}")
    #
    # header = [find_best_regions.s(data) for data in camera_list]
    # callback = do_nothing.s()
    # # logger.info(f"CALLBACK {type(callback)} {callback}")
    #
    # main_tasks_chord = chord(header, callback)
    # logger.info(f"main task chord {type(main_tasks_chord)}")
    #
    # # Create a chain to run the setup task first and then the chord of main tasks
    # # logger.info(f"setup {type(setup_task.s())}, main {type(main_tasks_chord)}")
    # workflow = chain(do_nothing.s(), main_tasks_chord)
    #
    # # Execute the workflow
    # workflow.apply_async()
    for cameras in camera_list:
        find_best_regions(cameras)


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

def save_suggested_values(camera_id, new_regions, new_matching_score, new_focus_value, new_light_level):
    suggested_values, created = SuggestedValues.objects.update_or_create(
        url_id=camera_id,
        defaults={
            'new_regions': new_regions,
            'new_matching_score': new_matching_score,
            'new_focus_value': new_focus_value,
            'new_light_level': new_light_level,
            'accepted': False
        }
    )

    if not created:
        suggested_values.current_regions = suggested_values.new_regions
        suggested_values.current_matching_score = suggested_values.new_matching_score
        suggested_values.current_focus_value = suggested_values.new_focus_value
        suggested_values.current_light_level = suggested_values.new_light_level

    suggested_values.save()


@shared_task()
def find_best_regions(camera_list):
    # cameras = Camera.objects.all()
    # camera_list = list(cameras.values_list('id', flat=True))
    start_time = time.time()
    logger.info(f"Stared find best regions  {len(camera_list)}")
    count = 0
    no_logs = 0
    ratio = 0
    # print(camera_list)
    no_regions = 0
    for camera_id in camera_list:
        reference_image_version = Camera.objects.get(pk=camera_id).reference_image_version
        reference_image_objects = ReferenceImage.objects.filter(url_id=camera_id, version=reference_image_version)
        logs = LogImage.objects.filter(url_id=camera_id, reference_image__in=reference_image_objects)

        # pass_count = logs.filter(action="Pass").count()
        # fail_count = logs.filter(action="Triggered").count()
        # capture_error_count = logs.filter(action="Capture Error").count()
        #
        # try:
        #     ratio_count = fail_count / (pass_count + fail_count + capture_error_count)
        # except ZeroDivisionError:
        #     ratio_count = 1
        average_scores = {}
        # if ratio_count < 0.01:
        #     # print(f"Low ratio count {ratio_count} {pass_count} {fail_count} {capture_error_count}")
        #     ratio += 1
        #     # ref_image = logs.last().reference_image
        #     # base_image = cv2.imread("/home/checkit/camera_checker/media/" + str(ref_image))
        #     # h, w, _c = base_image.shape
        #     # image = select_region.draw_grid([], base_image, h, w)
        #     # image = cv2.resize(image, (int(w/2),int(h/2)))
        #     # cv2.imshow("image", image)
        #     # cv2.waitKey(0)
        #     continue

        average_matching_scores = {}
        focus_values = []
        light_levels = []

        if not logs:
            # print("NO LOGS")
            no_logs += 1
            continue

        for log in logs:
            creation_date = log.creation_date
            action = log.action
            focus_value = log.focus_value
            light_level = log.light_level
            # potentially just work on cameras that have had a certain percentage of failures only.
            # no need to change those that are working.
            # do a count of pass and fail and if ratio is greater than 1/3 fail work on it
            if action not in ("Pass", "Triggered"):
                # print(f"Skipping - no Pass/Fail {action}")
                continue

            regions_score_values = list(json.loads(log.region_scores).values())
            focus_values.append(focus_value)
            light_levels.append(light_level)

            # Dictionary to store average scores for each cell

            # Populate the dictionary with scores for each cell
            # print(regions_score_values)
            for i, cell_value in enumerate(regions_score_values):
                cell_number = i + 1  # Cell numbering starts from 1
                if cell_number not in average_scores:
                    average_scores[cell_number] = []
                average_scores[cell_number].append(cell_value)

        if not average_scores:
            # print(f"Unable to find good region for camera, {camera_id} {average_scores}")
            continue
            # Calculate average scores for each cell and eliminate cells with scores below 0.5
        for cell_number, scores in average_scores.items():
            average_scores[cell_number] = np.mean(scores) if len(scores) > 0 else 0

        average_focus_value = round(sum(focus_values) / len(focus_values), 2)

        average_focus_value = round(average_focus_value * decimal.Decimal(.95)  ,2)
        if average_focus_value < .5:
            average_focus_value = .5


        average_light_level = round(sum(light_levels) / len(light_levels) * decimal.Decimal(.9), 2)
        average_light_level = round(average_light_level * decimal.Decimal(.95),2)
        # Group cells into quartiles based on average scores
        quartile_thresholds = np.percentile(list(average_scores.values()), [0, 25, 50, 75, 100])

        # Identify cells in the top quartile
        top_quartile_cells = [(cell_number, avg_score)  for cell_number, avg_score in average_scores.items() if
                              avg_score >= quartile_thresholds[3]]
        # print(f"{ratio_count}, {pass_count}, {fail_count}, {capture_error_count}, {top_quartile_cells}")

        skewness = skew(regions_score_values)
        new_matching_threshold = round(np.mean(regions_score_values) + skewness * np.std(regions_score_values), 2)
        new_matching_threshold = round(new_matching_threshold * 0.95,2)

        if new_matching_threshold <= 0.5 or new_matching_threshold > 0.8:
            if quartile_thresholds.min() <= 0.5:
                # print("Using base",0.5)
                new_matching_threshold = 0.5
            else:
                # print("Using quartile", quartile_thresholds.min())
                new_matching_threshold = round(quartile_thresholds.min() * 0.95, 2)


        # new_top_cells = top_quartile_cells
        ref_image = log.reference_image
        base_image = cv2.imread("/home/checkit/camera_checker/media/" + str(ref_image))
        original_base = base_image.copy()
        h, w, _c = base_image.shape
        cells = [cell[0] for cell in top_quartile_cells]
        c_list = select_region.get_coordinates(cells, h, w)

        # image = select_region.draw_grid(c_list, base_image, h, w)
        # cv2.imshow("grid", original_base)
        # cv2.waitKey(0)
        new_top_cells = []
        for i, cell in enumerate(c_list):
            (x, y), (qw, qh) = cell
            sub_img_frame = base_image[y:y + qh, x:x + qw]
            edges_in_cell = get_transparent_edge(sub_img_frame, (255, 255, 255))
            # cv2.imshow("cell", edges_in_cell)
            # cv2.waitKey(0)
            gray = cv2.cvtColor(edges_in_cell, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            num_white_pixels = cv2.countNonZero(binary)

            # if num_white_pixels > 50:
            #     new_top_cells.append(top_quartile_cells[i])
            if num_white_pixels > 100:
                new_top_cells.append((top_quartile_cells[i], num_white_pixels))
        sorted_data = sorted(new_top_cells, key=lambda x: (-x[0][1], -x[1]))
        prefered_cells = []
        if len(sorted_data) == 0:
            no_regions += 1
            # print("No regions found", no_regions)
            # cv2.imshow("No regions", base_image)
            # cv2.waitKey(0)

            continue
        prefered_matching_scores_list = []
        for item in islice(sorted_data, 4):
            prefered_cells.append(item[0][0])
            # print("Cell", item[0][0], "pixels", item[1])
            prefered_matching_scores_list.append(item[0][1])
        # skewness = skew(prefered_matching_scores_list)
        new_matching_threshold = round(np.mean(prefered_matching_scores_list), 2)
        new_matching_threshold = round(new_matching_threshold * 0.95, 2)
        # new_c_list = select_region.get_coordinates(prefered_cells, h, w)
        # image = select_region.draw_grid(new_c_list, base_image, h, w)
        # image = cv2.resize(image, (int(w/2),int(h/2)))
        # cv2.imshow("pref c", image)
        # cv2.waitKey(0)
        #
        # image = cv2.resize(image, (int(w / 2), int(h / 2)))

        # if new_top_cells != top_quartile_cells:
        # print(top_quartile_cells, new_top_cells)
        # cv2.imshow("Image", image)
        # cv2.waitKey(0)

        if isnan(new_matching_threshold):
            # print("Found invalid matching threshold")
            continue

        camera = Camera.objects.get(pk=camera_id)

        suggested_value = SuggestedValues()
        suggested_value.url = camera
        suggested_value.new_focus_value = average_focus_value
        suggested_value.new_light_level = average_light_level
        suggested_value.new_regions = prefered_cells
        suggested_value.new_matching_score = new_matching_threshold
        suggested_value.accepted = False
        suggested_value.current_focus_value = camera.focus_value_threshold
        suggested_value.current_light_level = camera.light_level_threshold
        suggested_value.current_regions = camera.image_regions
        suggested_value.save()
        # print("Best Regions Saved")
        count += 1
        # print(f'Done camera {camera_id}')
    # print(f"Processed {count} cameras - skipped no logs {no_logs} low ratio {ratio} - total {no_logs+count+ratio}")
    # print("Number of no region", no_regions)
    # print("Time", round(time.time() - start_time,2))

    return "Done"


def decode_frame(frame_data):
    process = (
        ffmpeg
        .input('pipe:0', format='h264')
        .output('pipe:1', format='image2', frames='1')
        .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
    )
    out, _ = process.communicate(input=frame_data)
    # print(_)
    if len(out) == 0:
        logger.info(f"Decode failed - {_}")
        return out, False

    return out, True


class RawSynAV2ComponentHeader:
    def __init__(self, data):
        self.FileID = data.decode('utf-8')


class RawSynAV2ComponentHeader2:
    def __init__(self, data):
        # Define the format string for struct.unpack
        fmt = '<10I'
        unpacked_data = struct.unpack(fmt, data)

        self.version_format_2ndID = unpacked_data[0]
        self.file_offset_supplementary_data = unpacked_data[1]
        self.file_offset_primary_index = unpacked_data[2]
        self.file_offset_configuration_data_index = unpacked_data[3]
        self.file_offset_authentication_data = unpacked_data[4]
        self.file_offset_configuration_data_entries = unpacked_data[5]
        self.number_of_entries_in_primary_index = unpacked_data[6]
        self.number_of_entries_in_configuration_index = unpacked_data[7]
        self.bytes_of_configuration_data_stored = unpacked_data[8]
        self.bits_of_presentation_timestamp = unpacked_data[9]


class ContentFrameHeader:
    def __init__(self, data):
        # Define the format string for struct.unpack
        fmt = '<IIIIHQ'
        unpacked_data = struct.unpack(fmt, data)

        self.file_offset_to_frame_entry = unpacked_data[0]
        self.frame_size = unpacked_data[1]
        self.frame_type_and_gop = unpacked_data[2]
        self.date_time = unpacked_data[3]
        self.seconds_and_frame_index = unpacked_data[4]
        self.bits_of_presentation_timestamp = unpacked_data[5]


class ContentFrameInPlaceHeader:
    def __init__(self, data):
        # Define the format string for struct.unpack
        fmt = '<I'
        unpacked_data = struct.unpack(fmt, data)

        self.S = unpacked_data[0] >> 1 & 0b1
        self.decoder_configuration_data_index = unpacked_data[0] >> 17 & 0b1111111111111111
        self.frame_time_stamp_millisecond = unpacked_data[0] >> 18 & 0b1111111111


class ConfigurationDataHeader:
    def __init__(self, data):
        fmt = '<II'
        unpacked_data = struct.unpack(fmt, data)

        self.offset = unpacked_data[0]
        self.size = unpacked_data[1]


def read_from_file(file_data):
    count = 0
    # logger.info(datetime.datetime.now())
    # logger.info(f"FILES {files}")
    # for file in files:
    # time.sleep(1)
    # logger.info(f"Reading file {file}")
    # with open(file, 'rb') as f:
    buffer = io.BytesIO(file_data)
    data = buffer.read(8)
    if len(data) < 8:
        # raise ValueError("File too short to contain a valid header")
        return None, "Error - File too short to contain a valid header"

    header = RawSynAV2ComponentHeader(data)
    # print(header.FileID)
    # print(count)
    if header.FileID != 'SYN-AV-2':
        logger.info("File ID is not SYN-AV-2")
        return None , "Error in Header"
    data = buffer.read(40)
    header2 = RawSynAV2ComponentHeader2(data)

    major_version = header2.version_format_2ndID & 0b1111  # bits 0-3
    minor_version = (header2.version_format_2ndID >> 4) & 0b1111  # bits 4-7
    stream_format = (header2.version_format_2ndID >> 8) & 0b11111111
    secondary_ID_tag_1st = (header2.version_format_2ndID >> 16) & 0b11111111
    secondary_ID_tag_2nd = (header2.version_format_2ndID >> 24) & 0b11111111
    # file_offset_supplementary_data = header2.file_offset_supplementary_data
    file_offset_primary_index = header2.file_offset_primary_index
    file_offset_configuration_data_index = header2.file_offset_configuration_data_index
    # file_offset_authentication_data = header2.file_offset_authentication_data
    file_offset_configuration_data_entries = header2.file_offset_configuration_data_entries
    number_of_entries_in_primary_index = header2.number_of_entries_in_primary_index
    number_of_entries_in_configuration_index = header2.number_of_entries_in_configuration_index
    bytes_of_configuration_data_stored = header2.bytes_of_configuration_data_stored
    # bits_of_presentation_timestamp = header2.bits_of_presentation_timestamp

    # print("Major Version:", major_version)
    # print("Minor Version:", minor_version)
    # print("Stream Format:", stream_format)
    # print("2nd ID Tag:", chr(secondary_ID_tag_1st) + chr(secondary_ID_tag_2nd))
    buffer.seek(file_offset_configuration_data_index)
    config_header_data = buffer.read(8)
    config_header = ConfigurationDataHeader(config_header_data)
    offset_within_configuration_data_entries = config_header.offset
    length_of_configuration_data = config_header.size
    buffer.seek(file_offset_configuration_data_entries)
    configuration_data = buffer.read(length_of_configuration_data)
    frame = bytearray(configuration_data)
    integer_value = int.from_bytes(configuration_data[0:4], byteorder='big')
    frame[0:4] = b'\x00\x00\x00\x01'
    start = integer_value + 4
    end = integer_value + 4 + 4
    frame[start:end] = b'\x00\x00\x00\x01'
    configuration_data = bytes(frame)
    buffer.seek(file_offset_primary_index)
    frames = []
    for frame_primary_index in range(number_of_entries_in_primary_index):
        data = buffer.read(26)
        frame_data_header = ContentFrameHeader(data)
        file_offset_to_frame_entry = frame_data_header.file_offset_to_frame_entry
        frame_size = frame_data_header.frame_size & 0b11111111111111111111111
        size_of_data = frame_data_header.frame_size >> 23
        frame_type = frame_data_header.frame_type_and_gop & 0b111
        frames.append((file_offset_to_frame_entry, frame_size, frame_type, size_of_data))
    frames_processed = 0
    # logger.info(f"frames {frames}")
    for frame_count, frame in enumerate(frames):
        # buffer.seek(frames[0][0])
        # inplace_header = ContentFrameInPlaceHeader(buffer.read(4))
        # can delete this loop later as we only want 1 frame anyway.
        # logger.info(f"frames_processed {frames_processed}")

        offset = frame[0]
        size = frame[1]
        # size_of_nal = 4

        buffer.seek(offset + 4)  # Add 4 bytes for Frame in place header.
        # now read the frame
        in_bytes = buffer.read(size)
        # logger.info(f"in_bytes length {len(in_bytes)}")
        # move the bytes into a bytearray, so we can manipulate the NAL's
        # frame = bytearray(in_bytes)

        nal_offset = 0
        nal_count = 0
        nal_positions = []
        frame = bytearray(in_bytes)

        while nal_offset < len(in_bytes):
            if nal_offset + 4 > len(in_bytes):
                return None, "Error in NAL offset"
            nal_size = int.from_bytes(in_bytes[nal_offset: nal_offset + 4], byteorder='big')
            if nal_offset + nal_size > len(in_bytes):
                return None, "Error in NAL offset"
            nal_count += 1
            nal_offset += nal_size + 4

            nal_positions.append(nal_offset)
            pass
        nal_positions.insert(0, 0)
        for position in nal_positions:
            frame[position:position + 4] = b'\x00\x00\x00\x01'

        in_bytes = bytes(frame)
        in_bytes = configuration_data + in_bytes

        image_bytes, status = decode_frame(in_bytes)

        if not image_bytes:
            logger.info("Error decoding video file",)
            return None, "Error Decoding"
        nparr = np.frombuffer(image_bytes, np.uint8)
        # Decode image from the NumPy array
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        h, w, _ = img.shape
        logger.info(count, "Decoded image", h, w)
        frames_processed += 1
        if frames_processed == 1:
            return img, "Success"
    return img, "Success"

def batch_delete_logs(queryset, batch_size=1000):
    log_count = 0
    while queryset.exists():
        ids = list(queryset[:batch_size].values_list('id', flat=True))
        if not ids:
            break
        LogImage.objects.filter(id__in=ids).delete()
        log_count += len(ids)
        if log_count % 100000 == 0:
            logger.info(f"Cleared {log_count} logs")
    return log_count


@shared_task(name='main_menu.tasks.clear_logs', time_limit=28800, soft_time_limit=28800)
def clear_logs():
    get_config()
    last_log_date = timezone.now() - datetime.timedelta(days=log_retention_period_days)
    # logs = LogImage.objects.filter(creation_date__lte=last_log_date)
    # print(len(logs))
    # number_of_logs = len(logs)
    # logs.delete()
    number_of_logs = batch_delete_logs(LogImage.objects.filter(creation_date__lte=last_log_date))
    engine_objects = EngineState.objects.filter(state_timestamp__lte=last_log_date)
    engine_objects.delete()
    # Camera.history.filter(history_date__lt=timezone.now() - timedelta(days=120)).delete()
    # LogImage.history.filter(history_date__lt=timezone.now() - timedelta(days=120)).delete()
    # ReferenceImage.history.filter(history_date__lt=timezone.now() - timedelta(days=120)).delete()
    LogEntry.objects.filter(action_time__lt=timezone.now() - timedelta(days=120)).delete()
    logger.info(f"Log file cleared from {last_log_date} - {number_of_logs} logs removed")
