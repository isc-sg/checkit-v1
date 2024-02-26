import time

from celery.utils.log import get_task_logger
from celery import shared_task
import mysql.connector

import cv2
import os
import sys
import configparser
import datetime
import math
import socket
from cryptography.fernet import Fernet
import subprocess
import hashlib
import ipaddress
from urllib.parse import urlparse
import base64
from wurlitzer import pipes
import skimage
from main_menu import select_region
from main_menu import a_eye
import json
import pathlib
import numpy as np
from scipy.signal import convolve2d
from scipy.ndimage import convolve
from scipy.stats import skew, kurtosis


from .models import ReferenceImage, LogImage, Camera, EngineState, Licensing
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
# from django.db import transaction
from django.conf import settings

# camera_list = [10023, 10024, 10025, 10026, 10027, 10028, 10029, 10030,
#                10031, 10032, 10033, 10034, 10035, 10036, 10037, 10038]


logger = get_task_logger(__name__)

MY_SDSN = 10101  # !!!! change this value to be the value of your SDSN (demo = 10101)
MY_PRODCODE = "DEMO"  # !!!! change this value to be the value of the Product Code in the dongle

socket_timeout = 1
CHECKIT_HOST = ""
HOST = ""
PORT = 0
network_interface = ""
log_alarms = False


def array_to_string(array):
    new_string = ""
    for element in array:
        new_string += chr(element)
    return new_string


checkit_array = [52, 50, 52, 48, 54, 55, 49, 49, 57, 53, 54, 116, 105, 107, 99, 101, 104, 67]

checkit_secret = array_to_string(checkit_array).encode()

checkit_key_array = [66, 117, 45, 86, 77, 100, 121, 83, 73, 80, 114, 101, 78, 103,
                     118, 101, 56, 119, 95, 70, 85, 48, 89, 45, 76, 72, 78, 118, 121,
                     103, 75, 108, 72, 105, 119, 80, 108, 74, 78, 79, 114, 54, 77, 61]

checkit_key = array_to_string(checkit_key_array).encode()


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

    # checkit_key = b'Bu-VMdySIPreNgve8w_FU0Y-LHNvygKlHiwPlJNOr6M='

    f = Fernet(checkit_key)
    machine_command_array = [47, 101, 116, 99, 47, 109, 97, 99, 104, 105, 110, 101, 45, 105, 100]
    machine_command = array_to_string(machine_command_array)
    # fd = open("/etc/machine-id", "r")
    # use ascii_to_string to obfuscate the command after compile
    fd = open(machine_command, "r")
    _machine_uuid = fd.read()
    _machine_uuid = _machine_uuid.strip("\n")
    shell_command_array = [47, 98, 105, 110, 47, 100, 102]
    shell_command_string = array_to_string(shell_command_array)
    # shell_output = subprocess.check_output("/bin/df", shell=True)
    shell_output = subprocess.check_output(shell_command_string, shell=True)
    # l1 = shell_output.decode('utf-8').split("\n")
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
    prod_uuid = subprocess.check_output(command, shell=True).decode(). \
        strip("\n").strip("\t").split("UUID:")[1].strip(" ")

    finger_print = (root_fs_uuid + _machine_uuid + prod_uuid)
    fingerprint_encrypted = get_encrypted(finger_print)
    db_password = fingerprint_encrypted[10:42][::-1]
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
                    "root_fs_uuid": root_fs_uuid,
                    "product_uuid": prod_uuid}
    string_encoded = f.encrypt(str(license_dict).encode())
    return _machine_uuid, root_fs_uuid, prod_uuid, string_encoded, db_password


machine_uuid, root_fs_uuid, product_uuid, encoded_string, mysql_password = get_license_details()

if not (machine_uuid and root_fs_uuid and product_uuid):
    logger.error("Licensing error - no license details - unable to proceed")
    sys.exit(1)


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

    return Camera.objects.filter(id__in=camera_list)


def check_license_ok():
    license_object = Licensing.objects.all().last()
    end_of_day_datetime_naive = datetime.datetime.combine(license_object.end_date, datetime.time.max)
    end_of_day_datetime = timezone.make_aware(end_of_day_datetime_naive, timezone.get_current_timezone())
    if license_object:
        if (license_object.transaction_count > license_object.transaction_limit or
           timezone.localtime() > end_of_day_datetime):
            return False
        else:
            return True


def send_alarms(cameras_details, run_number):

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

    alarm_logs = LogImage.objects.filter(run_number=run_number).exclude(action='Pass')
    for alarm in alarm_logs:
        url_id = alarm.url_id
        log_image = alarm.image
        matching_score = alarm.matching_score
        focus_value = alarm.focus_value
        light_level = alarm.light_level
        reference_image_id = alarm.reference_image_id

        last_good_check = LogImage.objects.filter(url_id=url_id, action="Pass").last()

        if last_good_check:
            last_good_check_date_time = last_good_check.creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            last_good_check_date_time = "NONE"

        camera_url = cameras_details.get(id=url_id).url
        camera_number = cameras_details.get(id=url_id).camera_number
        camera_name = cameras_details.get(id=url_id).camera_name
        camera_location = cameras_details.get(id=url_id).camera_location

        if reference_image_id:
            reference_image_object = ReferenceImage.objects.get(pk=reference_image_id)
            reference_image = reference_image_object.image
            reference_image_creation_date = reference_image_object.creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            reference_image = [""]
            reference_image_creation_date = ""

        additional_data = ("lastGoodCheckDatetime=" + last_good_check_date_time +
                           "&amp;referenceImageDatetime=" + reference_image_creation_date)

        image = "http://" + CHECKIT_HOST + "/media/" + log_image
        reference_image = "http://" + CHECKIT_HOST + "/media/" + reference_image

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
            s.connect((HOST, PORT))
            s.send(send_alarm.encode())
            reply = s.recv(8192).decode().rstrip("\x00")
            logger.info(f"Reply for Alarm Server {reply}")
        except socket.error as e:
            logger.error(f"Error sending to alarm server - {e}")


def increment_transaction_count():

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


def log_capture_error(camera, user, engine_state_id, message):
    LogImage.objects.create(url_id=camera, region_scores=[], action="Capture Error",
                            creation_date=timezone.now(), user=user, run_number=engine_state_id)
    increment_transaction_count()
    logger.error(message)


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
    time.sleep(3)
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

    focus_value = skimage.measure.blur_effect(frame)
    focus_value = round(focus_value, 2)

    blur = cv2.blur(frame, (5, 5))
    light_level = cv2.mean(blur)[0]

    return {"matching score": matching_score, "focus value": focus_value,
            "region scores": region_scores, "light level": light_level, "noise_level": noise_level}


def create_base_image(camera_object, capture_device):

    logger.info(f"Attempting capture of reference image for {camera_object.url} - "
                f"camera number {camera_object.camera_number}")
    time.sleep(3)

    able_to_read, frame = capture_device.read()
    if not able_to_read:
        logger.error(f"Unable to read from device for "
                     f"camera id {camera_object.id} / camera number {camera_object.camera_number}")
        return

    logger.debug(f"Successfully captured reference image on"
                 f" {camera_object.camera_name} {camera_object.id} {camera_object.camera_number}")

    base_image_dir = f"{settings.MEDIA_ROOT}/base_images"

    file_name = f"{base_image_dir}/{camera_object.id}/{timezone.localtime().strftime('%H')}.jpg"
    try:
        pathlib.Path(base_image_dir+f"/{camera_object.id}").mkdir(parents=True, exist_ok=True)
        os.system(f"sudo chmod 775 {base_image_dir}/{camera_object.id}")
    except Exception as e:
        logger.error(f"Unable to create or set permissions on reference image directory {e}")
        return

    if os.path.isfile(file_name):
        os.remove(file_name)
    else:

        try:
            os.system(f"sudo chmod 775 {base_image_dir}/{camera_object.id}")
        except Exception as e:
            logger.error(f"Unable to set permissions on {base_image_dir}/{camera_object.id} {e}")
            return

        able_to_write = cv2.imwrite(file_name, frame)

        if not able_to_write:
            logger.error(f"Unable to save reference image for id {camera_object.id} / "
                         f" camera number {camera_object.camera_number}")
            return

        try:

            img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.blur(img_gray, (5, 5))
            base_brightness = cv2.mean(blur)[0]

            noise_level = estimate_noise(frame)
            # logger.info(f"Noise Level {noise_level}")
            focus_value = skimage.measure.blur_effect(img_gray)
            focus_value = round(focus_value, 2)

            image_file_name = file_name.strip(f"{settings.MEDIA_ROOT}/")

            ReferenceImage.objects.create(url_id=camera_object.id, image=image_file_name,
                                          hour=timezone.localtime().strftime('%H'),
                                          light_level=base_brightness,
                                          creation_date=timezone.now(), focus_value=focus_value, version=1)
            # create log entry here with action as REFERENCE IMAGE
        except Exception as e:
            logger.error(f"Unable to save reference image {file_name} for camera id {camera_object.id} - error {e}")
            # remove file created earlier as transaction failed.
            if os.path.isfile(file_name):
                os.remove(file_name)


def read_frame_and_compare(capture_device, user, engine_state_id, camera_object):
    multicast_address = camera_object.multicast_address
    camera = camera_object.id
    regions = camera_object.image_regions
    able_to_read, image_frame = capture_device.read()
    current_hour = str(timezone.localtime().hour).zfill(2)

    if not able_to_read:
        message = "Error reading video frame\n"
        log_capture_error(camera, user, engine_state_id, message)
        increment_transaction_count()
        close_capture_device(capture_device, multicast_address)
        return

    if regions == '0' or regions == "[]":
        regions = []
        regions.extend(range(1, 65))
    else:
        regions = eval(regions)

    reference_image_objects = ReferenceImage.objects.filter(url_id=camera)
    # alternative method to do the above is to do the following
    # camera.referenceimage_set.all()
    # referenceimage_set is created by Django automatically.
    if not reference_image_objects.filter(hour=current_hour).exists():
        create_base_image(camera_object, capture_device)
        close_capture_device(capture_device, multicast_address)
        return

    file_name = reference_image_objects.get(hour=current_hour).image
    base_image_name = f"{settings.MEDIA_ROOT}/{file_name}"
    base_image = cv2.imread(base_image_name)
    if base_image is None:
        message = "Error reading reference image\n"
        log_capture_error(camera, user, engine_state_id, message)
        increment_transaction_count()
        close_capture_device(capture_device, multicast_address)
        return

    # check if image is low res
    h, w = image_frame.shape[:2]
    if h < 720:
        scale = math.ceil(720 / h)
        logger.info(f"WARNING: Image size is below recommended minimum of 720p - "
                    f"images are being scaled up by factor of {scale} for analysis")
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
        logger.error(f"Error in converting image {err}")
        increment_transaction_count()
        close_capture_device(capture_device, multicast_address)
        return

    if reference_dimensions != capture_dimensions:
        logger.error(
            f"Image sizes don't match on camera number {camera}")
        LogImage.objects.create(url_id=camera, region_scores={},
                                action="Image Size Error",
                                creation_date=timezone.now(), user=user,
                                run_number=engine_state_id)
        increment_transaction_count()
        close_capture_device(capture_device, multicast_address)
        return

    # Do the check here
    results_dict = compare_images(image_base_grey, image_frame_grey, regions)
    matching_score = results_dict['matching score']
    focus_value = results_dict['focus value']
    region_scores = results_dict['region scores']
    light_level = results_dict['light level']
    base_image_directory = (f"{settings.MEDIA_ROOT}/log/{timezone.now().year}"
                            f"/{timezone.now().month}/{timezone.now().day}")
    log_image_file_name = (f"{base_image_directory}/"
                           f"{camera}-"
                           f"{timezone.now().hour}:{timezone.now().minute}:{timezone.now().second}.jpg")

    try:
        pathlib.Path(f"{base_image_directory}").mkdir(parents=True, exist_ok=True)
        os.system(f"sudo chmod 775 {base_image_directory}")
    except Exception as e:
        logger.error(f"Unable to create or set permissions on log directory {base_image_directory} - {e}")
        return

    able_to_write = cv2.imwrite(log_image_file_name, image_frame)
    if not able_to_write:
        logger.error(f"Unable to write log file {log_image_file_name}")
        increment_transaction_count()
        close_capture_device(capture_device, multicast_address)
        return

    sql_file_name = log_image_file_name.strip(settings.MEDIA_ROOT)

    if matching_score < camera_object.matching_threshold:
        action = "Failed"
    elif focus_value > camera_object.focus_value_threshold:
        action = "Failed"
    elif light_level < camera_object.light_level_threshold:
        action = "Failed"
    else:
        action = "Pass"

    LogImage.objects.create(url_id=camera, image=sql_file_name,
                            matching_score=matching_score,
                            region_scores=json.dumps(region_scores),
                            current_matching_threshold=camera_object.matching_threshold,
                            light_level=light_level,
                            focus_value=focus_value,
                            action=action,
                            creation_date=timezone.now(),
                            current_focus_value=camera_object.focus_value_threshold,
                            current_light_level=camera_object.light_level_threshold,
                            user=user,
                            run_number=engine_state_id,
                            reference_image_id=reference_image_objects.get(hour=current_hour).id)

    increment_transaction_count()

    camera_object = Camera.objects.get(id=camera)
    camera_object.last_check_date = timezone.now()
    camera_object.save()
    close_capture_device(capture_device, multicast_address)
    logger.info(f"Checked camera {camera}")


def check_cameras(camera_list, cameras_details, engine_state_id, user):

    logger.info(f"Starting check {camera_list}")

    for camera in camera_list:
        camera_object = cameras_details.get(id=camera)
        url = camera_object.url
        camera_number = camera_object.camera_number
        multicast_address = camera_object.multicast_address
        multicast_port = camera_object.multicast_port
        camera_username = camera_object.camera_username
        camera_password = camera_object.camera_password
        hoursinday = list(camera_object.scheduled_hours.values_list('hour_in_the_day', flat=True))
        daysofweek = list(camera_object.scheduled_days.values_list('id', flat=True))

        if int(timezone.localtime().hour) not in hoursinday:
            continue
        if (timezone.localtime().weekday() + 1) not in daysofweek:
            continue
        if camera_object.snooze:
            continue

        # if user has entered a username and password set in the database then ensure that we use these
        # when we connect via the url. Add username and password to URL.

        if camera_username and camera_password:
            url_parts = url.split("//")
            url = f"{url_parts[0]}//{camera_username}:{camera_password}@{url_parts[1]}"

        ip_address, url_port, scheme = extract_ip_from_url(url)

        if ip_address == "Error":
            message = (f"Error in IP address for camera "
                       f"{camera_object.camera_name} {camera_number} {camera_object.id}")
            log_capture_error(camera, user, engine_state_id, message)
            increment_transaction_count()
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
            logger.error(f"Unsupported URL scheme {scheme}")
            return

        if scheme in ["rtsp", "rtsps"]:
            options_response, has_error = options(url, ip_address, url_port, camera_username, camera_password)
            if has_error:
                message = f"Error in OPTIONS for {url} {options_response}\n"
                log_capture_error(camera, user, engine_state_id, message)
                increment_transaction_count()
                continue

            describe_response, has_error = describe(url, ip_address, url_port, camera_username, camera_password)
            if has_error:
                message = f"Error in DESCRIBE for url {url} {describe_response}"
                log_capture_error(camera, user, engine_state_id, message)
                increment_transaction_count()
                continue

            capture_device = open_capture_device(url, multicast_address, multicast_port, describe_response)

            if capture_device == "Error" or not capture_device.isOpened():
                message = f"Unable to open capture device {url}\n"
                log_capture_error(camera, user, engine_state_id, message)
                increment_transaction_count()
                close_capture_device(capture_device, multicast_address)
                continue

            read_frame_and_compare(capture_device, user, engine_state_id, camera_object)
            # able_to_read, image_frame = capture_device.read()
            #
            # if not able_to_read:
            #     message = "Error reading video frame\n"
            #     log_capture_error(camera, user, engine_state_id, message)
            #     increment_transaction_count()
            #     close_capture_device(capture_device, multicast_address)
            #     continue
            #
            # if regions == '0' or regions == "[]":
            #     regions = []
            #     regions.extend(range(1, 65))
            # else:
            #     regions = eval(regions)
            #
            # reference_image_objects = ReferenceImage.objects.filter(url_id=camera)
            # if not reference_image_objects.filter(hour=timezone.localtime().hour).exists():
            #     create_base_image(camera_object,  capture_device)
            #     close_capture_device(capture_device, multicast_address)
            #     continue
            #
            # file_name = reference_image_objects.get(hour=timezone.localtime().hour).image
            # base_image = cv2.imread("/home/checkit/camera_checker/media/" + file_name)
            # if not base_image:
            #     message = "Error reading reference image\n"
            #     log_capture_error(camera, user, engine_state_id, message)
            #     increment_transaction_count()
            #     close_capture_device(capture_device, multicast_address)
            #     continue
            #
            # # check if image is low res
            # h, w = image_frame.shape[:2]
            # if h < 720:
            #     scale = math.ceil(720 / h)
            #     logger.info(f"WARNING: Image size is below recommended minimum of 720p - "
            #                 f"images are being scaled up by factor of {scale} for analysis")
            #     image_frame = cv2.resize(image_frame, (h * scale, w * scale),
            #                              interpolation=cv2.INTER_AREA)
            #     base_image = cv2.resize(base_image, (h * scale, w * scale),
            #                             interpolation=cv2.INTER_AREA)
            #
            # # prepare images for checking - need grey scale
            # try:
            #     image_base_grey = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
            #     image_frame_grey = cv2.cvtColor(image_frame, cv2.COLOR_BGR2GRAY)
            #     reference_dimensions = image_base_grey.shape[:2]
            #     capture_dimensions = image_frame_grey.shape[:2]
            # except cv2.error as err:
            #     logger.error(f"Error in converting image {err}")
            #     increment_transaction_count()
            #     close_capture_device(capture_device, multicast_address)
            #     continue
            #
            # if reference_dimensions != capture_dimensions:
            #     logger.error(
            #         f"Image sizes don't match on camera number {camera}")
            #     LogImage.objects.create(url_id=camera, region_scores={},
            #                             action="Image Size Error",
            #                             creation_date=timezone.now(), user=user,
            #                             run_number=engine_state_id)
            #     increment_transaction_count()
            #     close_capture_device(capture_device, multicast_address)
            #     continue
            #
            # # Do the check here
            # results_dict = compare_images(image_base_grey, image_frame_grey, regions)
            # matching_score = results_dict['matching score']
            # focus_value = results_dict['focus value']
            # region_scores = results_dict['region scores']
            # light_level = results_dict['light level']
            # log_image_file_name = (f"{settings.MEDIA_ROOT}/log/{timezone.now().year}/{timezone.now().month}/"
            #                        f"{timezone.now().day}/{camera}-"
            #                        f"{timezone.now().hour}:{timezone.now().minute}:{timezone.now().second}.jpg")
            #
            # sql_file_name = log_image_file_name.strip(settings.MEDIA_ROOT)
            #
            # if matching_score < camera_object.matching_threshold:
            #     action = "Failed"
            # elif focus_value > camera_object.focus_value_threshold:
            #     action = "Failed"
            # elif light_level < camera_object.light_level_threshold:
            #     action = "Failed"
            # else:
            #     action = "Pass"
            #
            # LogImage.objects.create(url_id=camera, image=sql_file_name,
            #                         matching_score=matching_score,
            #                         region_scores=json.dumps(region_scores),
            #                         current_matching_threshold=camera_object.matching_threshold,
            #                         light_level=light_level,
            #                         focus_value=focus_value,
            #                         action=action,
            #                         creation_date=timezone.now(),
            #                         current_focus_value=camera_object.focus_value_threshold,
            #                         current_light_level=camera_object.light_level_threshold,
            #                         user=user,
            #                         run_number=engine_state_id,
            #                         reference_image_id=reference_image_objects.get(hour=timezone.localtime().hour).id)
            #
            # increment_transaction_count()
            #
            # camera_object = Camera.objects.get(id=camera)
            # camera_object.last_check_date = timezone.now()
            # camera_object.save()
            # close_capture_device(capture_device, multicast_address)

        else:
            # this should be simple imread rather than open / describe etc.
            if camera_object.multicast_address:
                logger.error(f"{scheme} over multicast is currently not supported")
                return
            capture_device = cv2.VideoCapture(camera_object.url)
            read_frame_and_compare(capture_device, user, engine_state_id, camera_object)


@shared_task()
def process_cameras(camera_list, engine_state_id, user_name):
    get_config()

    if check_license_ok():
        # ret_code = ProtCheck()
        # logger.info(f"ret_code {ret_code}")
        # if ret_code != 0:
        #     return f"Licensing Error {ret_code}"
        # logger.info(f"{cameras}{engine_state_id}{user_name}")
        worker_id = process_cameras.request.hostname
        logger.info(f"Worker ID: {worker_id} Cameras {camera_list}")
        cameras_details = get_camera_details(camera_list)
        if not cameras_details:
            logger.info(f'"Error - camera list does not contain any cameras" - {camera_list}')
            sys.exit(1)

        check_cameras(camera_list, cameras_details, engine_state_id, user_name)

        logs = LogImage.objects.filter(run_number=engine_state_id)
        number_of_pass = logs.filter(action="Pass").count()
        number_of_fail = logs.filter(action="Failed").count()
        number_of_others = logs.count() - (number_of_pass + number_of_fail)
        if logs:
            last_log_time = logs.last().creation_date
            engine_start_time = EngineState.objects.get(id=engine_state_id - 1).state_timestamp
            transaction_rate = math.floor(len(logs) / (last_log_time.timestamp() - engine_start_time.timestamp()))

            try:
                engine_object = EngineState.objects.all().last()
                engine_object.transaction_rate = transaction_rate
                engine_object.number_pass_images = number_of_pass
                engine_object.number_failed_images = number_of_fail
                engine_object.number_others = number_of_others
                engine_object.state_timestamp = timezone.now()
                engine_object.save()
            except EngineState.DoesNotExist:
                logger.error(f"Error updating transaction rate")

        if log_alarms:
            send_alarms(cameras_details, engine_state_id)

    else:
        logger.error(f"You license has either expired or exhausted the available transactions")
