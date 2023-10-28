import ast
import datetime
import subprocess
import time
from subprocess import PIPE, Popen
import csv
import os
import io
import base64
import logging
from logging.handlers import RotatingFileHandler
from bisect import bisect_left
import cv2
import numpy as np
import uuid
import mysql.connector

from django.http import HttpResponse, HttpResponseRedirect, FileResponse, Http404, JsonResponse
from django.template import loader
from django.shortcuts import render, reverse, redirect
from tablib import Dataset
from django_tables2 import SingleTableMixin
from django_filters.views import FilterView
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.views.decorators.cache import cache_control
from django.contrib.auth.models import Permission, User, Group

from .resources import CameraResource
from .models import EngineState, Camera, LogImage, Licensing, ReferenceImage, DaysOfWeek, HoursInDay
from .tables import CameraTable, LogTable, EngineStateTable, CameraSelectTable
from .forms import DateForm, RegionsForm
from .filters import CameraFilter, LogFilter, EngineStateFilter, CameraSelectFilter
import main_menu.select_region as select_region

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor
import hashlib
import json
from cryptography.fernet import Fernet, InvalidToken

from zipfile import ZipFile, ZIP_DEFLATED

from rest_framework import viewsets
from rest_framework import permissions
from rest_framework.parsers import JSONParser

from main_menu.serializers import CameraSerializer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

error_image = np.zeros((720, 1280, 3), np.uint8)

error_image = cv2.putText(error_image, "Error retrieving image",
                          (250, 300), cv2.FONT_HERSHEY_TRIPLEX, 2,
                          (0, 0, 255), 2, cv2.LINE_AA)

checkit_secret = "Checkit65911760424"[::-1].encode()

key = b'Bu-VMdySIPreNgve8w_FU0Y-LHNvygKlHiwPlJNOr6M='

#
# class UserViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint that allows users to be viewed or edited.
#     """
#     queryset = User.objects.all().order_by('-date_joined')
#     serializer_class = UserSerializer
#     permission_classes = [permissions.IsAuthenticated]


class CameraViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows cameras to be viewed or edited.
    """
    queryset = Camera.objects.all().order_by('camera_number')
    serializer_class = CameraSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'camera_number'


def custom_500_error_view(request):
    return render(request, '500.html')


def reference_image_api(request):
    if request.method == "POST":
        if 'action' not in request.POST:
            return HttpResponse("Error: requires action field")
        action: str = request.POST['action']
        if action.lower() not in ("delete", "refresh"):
            return HttpResponse("Error: action needs to be either delete or refresh")
        if 'camera_number' in request.POST:
            camera_number = request.POST['camera_number']
        else:
            camera_number = None
        try:
            camera_object = Camera.objects.get(camera_number=camera_number)
        except ObjectDoesNotExist:
            return HttpResponse("Error: camera does not exist")
        if action.lower() == "refresh":
            child_process = Popen(["/home/checkit/env/bin/python",
                                   "/home/checkit/camera_checker/main_menu/start.py", camera_number],
                                  stdout=PIPE, stderr=PIPE)
            stdout, stderr = child_process.communicate()
            return_code = child_process.returncode
            # print('return_code', return_code)
            if return_code == 33:
                return HttpResponse("Error: Licensing Error")
            elif return_code == 0:
                logging.info(f"API request completed camera check for camera {camera_number}")
                process_output = "Run Completed - No errors reported"
                logging.info("Process Output {p}".format(p=process_output))
                return HttpResponse(process_output)
            else:
                logging.error("Error in camera check for camera {} - {}".format(camera_number, stderr))
                return HttpResponse("Error in camera check for camera {} - {}".format(camera_number, stderr))
        elif action.lower() == "delete":
            if "hour" not in request.POST:
                return HttpResponse("Error: please provide hour for delete action")
            else:
                hour = request.POST['hour']
                # look up reference image and make sure it exists.
                try:
                    reference_image_object = ReferenceImage.objects.get(url_id=camera_object.id, hour=hour)
                    try:
                        reference_image_object.delete()
                    except Exception:
                        return HttpResponse("Error: unable to delete reference image")
                    return HttpResponse("Success")
                except ObjectDoesNotExist:
                    return HttpResponse(f"Error: reference image for camera number "
                                        f"{camera_number} and hour {hour} does not exist")
    else:
        return HttpResponse("Error: Only POST method allowed")


def get_hash(key_string):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(key_string.encode())
    return h.hexdigest().upper()


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
            logging.error(f"Failed all attempts at accessing database  {e}")
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
    return current_transaction_count, current_transaction_limit, current_end_date, current_camera_limit, current_license_key


def get_encrypted(password):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(password.encode())
    h_in_hex = h.hexdigest().upper()
    return h_in_hex


def get_license_details():
    f = Fernet(key)

    fd = open("/etc/machine-id", "r")
    machine_uuid = fd.read()
    machine_uuid = machine_uuid.strip("\n")

    shell_output = subprocess.check_output("/bin/df", shell=True)
    l1 = shell_output.decode('utf-8').split("\n")
    command = "mount | sed -n 's|^/dev/\(.*\) on / .*|\\1|p'"
    root_dev = subprocess.check_output(command, shell=True).decode().strip("\n")

    command = "/usr/bin/sudo /sbin/blkid | grep " + root_dev
    root_fs_uuid = subprocess.check_output(command, shell=True).decode().split(" ")[1].split("UUID=")[1].strip("\"")

    command = "/usr/bin/sudo dmidecode | grep -i uuid"
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


def get_base_image(reference_images_list, url_id, regions):
    time_stamp = datetime.datetime.now()
    hour = time_stamp.strftime('%H')
    hours = []
    for record in reference_images_list:
        hours.append(record.hour)
    for i in range(0, len(hours)):
        hours[i] = int(hours[i])
    hour = int(hour)
    hours.sort()

    closest_hour = take_closest(hours, hour)
    closest_hour = str(closest_hour).zfill(2)
    try:
        closest_reference_image = ReferenceImage.objects.get(url_id=url_id, hour=closest_hour)

        image = closest_reference_image.image
        base_image_file = settings.MEDIA_ROOT + "/" + str(image)
        img = cv2.imread(base_image_file)

        regions = eval(regions)
        height, width, channels = img.shape

        co_ordinates = select_region.get_coordinates(regions, height, width)

        image = select_region.draw_grid(co_ordinates, img, height, width)

    except ObjectDoesNotExist:
        image = error_image

    img_cv2_converted_to_binary = cv2.imencode('.jpg', image)[1]
    return base64.b64encode(img_cv2_converted_to_binary).decode('utf-8')


def coord(x, y, h, unit=1):
    x, y = x * unit, h - y * unit
    return x, y


def get_user_permissions(user):
    if user.is_superuser:
        return Permission.objects.all()
    return user.user_permissions.all() | Permission.objects.filter(group__user=user)


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




def index(request):
    # user_name = request.user.username
    # logging.info("User {u} access to System Status".format(u=user_name))
    statvfs = os.statvfs('/home/checkit')

    total_disk_giga_bytes = statvfs.f_frsize * statvfs.f_blocks / (1024 * 1024 * 1024)
    total_disk_giga_bytes_free = round(statvfs.f_frsize * statvfs.f_bavail / (1024 * 1024 * 1024), 2)
    total_disk_giga_bytes_used = round(total_disk_giga_bytes - total_disk_giga_bytes_free, 2)
    template = loader.get_template('main_menu/dashboard.html')
    obj = EngineState.objects.last()
    if request.user.is_superuser:
        # print("is super")
        admin_user = "True"
    else:
        admin_user = "False"
    if request.method == 'POST' and 'download_logs' in request.POST:
        log_files = ["/home/checkit/camera_checker/logs/checkit.log",
                     "/var/log/monit.log",
                     "/var/log/syslog",
                     "/var/log/kern.log",
                     "/var/log/auth.log",
                     "/var/log/apache2/access.log",
                     "/var/log/apache2/error.log",
                     ]
        log_file_zipped = "/tmp/logs.zip"
        with ZipFile(log_file_zipped, "w", ZIP_DEFLATED) as archive:
            for log_file in log_files:
                try:
                    archive.write(log_file)
                except FileNotFoundError:
                    logging.info("Logfile {f} does not exist".format(f=log_file))
        if os.path.exists(log_file_zipped):
            with open(log_file_zipped, 'rb') as fh:
                response = HttpResponse(fh.read(), content_type="application/octet-stream")
                response['Content-Disposition'] = 'inline; filename=' + os.path.basename(log_file_zipped)
                return response
        raise Http404
    if obj is not None:
        state = obj.state
        context = {'system_state': state.title(), 'used': total_disk_giga_bytes_used,
                   'free': total_disk_giga_bytes_free,
                   'total': total_disk_giga_bytes, "admin_user": admin_user}
    else:
        context = {'system_state': "Run Completed", 'used': total_disk_giga_bytes_used,
                   'free': total_disk_giga_bytes_free, 'total': total_disk_giga_bytes, "admin_user": admin_user}
    return HttpResponse(template.render(context, request))


def simple_upload(request):
    if request.method == 'POST':
        # user_name = request.user.username
        # logging.info("User {u} access to Upload".format(u=user_name))
        camera_resource = CameraResource()
        dataset = Dataset()
        new_cameras = request.FILES['my_file']

        imported_data = dataset.load(new_cameras.read(), format='csv', headers=True)
        print(imported_data)
        result = camera_resource.import_data(dataset, dry_run=True)  # Test the data import

        if not result.has_errors():
            camera_resource.import_data(dataset, dry_run=False)  # Actually import now

    return render(request, 'main_menu/import.html')


@cache_control(private=True)
def compare_images(request):
    template = loader.get_template('main_menu/display_reference_and_capture.html')
    if request.method == 'POST':
        record_id = request.POST.get('record')
        obj = LogImage.objects.get(id=record_id)
        region_scores = obj.region_scores
        result = obj.action
        hour = obj.creation_date.hour
        cam = obj.url_id
        camera_object = Camera.objects.get(pk=cam)
        camera_name = camera_object.camera_name
        camera_number = camera_object.camera_number

        # time_stamp = datetime.datetime.now()
        # hour = time_stamp.strftime('%H')
        reference_images = ReferenceImage.objects.filter(url_id=camera_object.id)
        hours = []
        # TODO: need error checking if there are no reference images
        for record in reference_images:
            hours.append(record.hour)
        for i in range(0, len(hours)):
            hours[i] = int(hours[i])
        hour = int(hour)
        if hours:
            absolute_difference_function = lambda list_value: abs(list_value - hour)
            closest_hour = min(hours, key=absolute_difference_function)
            closest_hour = str(closest_hour).zfill(2)
            reference_images = ReferenceImage.objects.get(url_id=camera_object.id, hour=closest_hour)
            image = reference_images.image
            base_image = cv2.imread(settings.MEDIA_ROOT + "/" + str(image))
            if base_image is None:
                context = {'result': "Capture Error", 'camera_name': camera_name,
                           'message': " - Unable to read BASE image"}
                return HttpResponse(template.render(context, request))

            captured_image = cv2.imread(settings.MEDIA_ROOT + "/" + str(obj.image))
            if captured_image is None:
                context = {'result': "Capture Error", 'camera_name': camera_name,
                           'message': " - Unable to read LOG image"}
                return HttpResponse(template.render(context, request))

            captured_image_transparent = get_transparent_edge(captured_image, [0, 0, 255])

            captured_image_transparent = captured_image_transparent[:, :, :3]

            if captured_image_transparent.shape != base_image.shape:
                context = {'result': "Image Size Error", 'camera_name': camera_name,
                           'message': " - Base image and capture image size changed"}
                return HttpResponse(template.render(context, request))

            merged_image = cv2.addWeighted(captured_image_transparent, 1, base_image, 1, 0)
            merged_image_converted_to_binary = cv2.imencode('.png', merged_image)[1]
            base_64_merged_image = base64.b64encode(merged_image_converted_to_binary).decode('utf-8')
            context = {'capture_image': obj.image, 'reference_image': image, 'result': result,
                       'camera_name': camera_name, 'camera_number': camera_number, 'merged_image': base_64_merged_image}
        else:
            context = {'result': result, 'camera_name': camera_name, 'camera_number': camera_number}
        return HttpResponse(template.render(context, request))
    else:
        return redirect('logs')


# @permission_required('camera_checker.main_menu')
def scheduler(request):
    user_name = request.user.username
    # permissions = get_user_permissions(request.user)
    # print(permissions)
    if request.user.is_superuser:
        admin_user = "True"
    else:
        admin_user = "False"

    logging.info("User {u} access to Scheduler".format(u=user_name))

    template = loader.get_template('main_menu/scheduler.html')
    # get the actual state from the engine here and pass it to context
    obj = EngineState.objects.last()
    if obj is not None:
        state = obj.state.title()
    else:
        state = "Run Completed"
    license_obj = Licensing.objects.last()
    # run_schedule = license_obj.run_schedule
    # tmp_file_name = "/tmp/" + str(uuid.uuid4())
    command = "/usr/bin/crontab -l"
    # tmp_file = open(tmp_file_name, "w")
    # tmp_file.write(command)
    # tmp_file.close()
    try:
        # logging.info("process")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = process.communicate()
        # logging.info(out, err)
        err = err.decode()[:14]
        if err == "no crontab for":
            scheduler_status = "Scheduler Off"
        elif out == b"":
            scheduler_status = "Scheduler Off"
        else:
            scheduler_status = "Scheduler Running"
    except:
        logging.error("crontab look up failed")
    context = {'system_state': state,
               "scheduler_status": scheduler_status, "admin_user": admin_user}

    # can use pid method to check if actually running. see compare_images_v2
    if request.method == 'POST' and 'toggle_scheduler' in request.POST:
        # logging.info("toggle scheduler")
        try:
            # tmp_file_name = "/tmp/" + str(uuid.uuid4())
            command = "/usr/bin/crontab -l"
            # tmp_file = open(tmp_file_name, "w")
            # tmp_file.write(command)
            # tmp_file.close()
            # logging.info("about to proc")

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            # process.wait()
            out, err = process.communicate()
            # logging.info("done proc", process.returncode)

            # logging.info("out,err", out, err)
            # logging.info("error on communicate")
            err = err.decode()[:14]
            if err == "no crontab for":
                # logging.info("Turning on")
                tmp_file_name = "/tmp/" + str(uuid.uuid4())
                command = "0 */1 * * * /home/checkit/env/bin/python " \
                          "/home/checkit/camera_checker/main_menu/start.py \n"
                fd = open(tmp_file_name, "w")
                fd.write(command)
                fd.close()

                command = "/usr/bin/crontab " + tmp_file_name
                # logging.info(command)
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                time.sleep(1)
                try:
                    os.remove(tmp_file_name)
                except OSError:
                    pass
                return HttpResponseRedirect(reverse(scheduler))
            else:
                # logging.info("Turning off")
                # tmp_file_name = "/tmp/" + str(uuid.uuid4())
                command = "/usr/bin/crontab -r"
                # tmp_file = open(tmp_file_name, "w")
                # tmp_file.write(command)
                # tmp_file.close()
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                # out, err = process.communicate()
                # logging.info("did cron")
                return HttpResponseRedirect(reverse(scheduler))
        except:
            logging.error("crontab look up failed")
    if request.method == 'POST' and 'start_engine' in request.POST:
        logging.info("User {u} started engine".format(u=user_name))
        # subprocess.Popen(["nohup", "/home/checkit/camera_checker/main_menu/compare_images_v2.bin"])
        # process_output = subprocess.check_output(["/home/checkit/env/bin/python",
        #                                           "/home/checkit/camera_checker/main_menu/start.py"])
        process = Popen(["/home/checkit/env/bin/python",
                         "/home/checkit/camera_checker/main_menu/start.py"], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        return_code = process.returncode
        # print('return_code', return_code)
        if return_code == 33:
            context = {"error": "Licensing Error"}
            return HttpResponse(template.render(context, request))
        elif return_code == 0:
            logging.info(f"User {user_name} completed camera check for all cameras")
            process_output = "Run Completed - No errors reported"
            logging.info("Process Output {p}".format(p=process_output))
            return HttpResponseRedirect(reverse(index))
            # if process_output.decode() == '':
            #     process_output = "Run Completed - No errors reported"
        else:
            logging.error("Error in camera check for all cameras - {}".format(stderr))
            context = {"error": "Error Checking Camera"}
            return HttpResponse(template.render(context, request))

    # if request.method == 'POST' and 'new_run' in request.POST:
    #     new_run_schedule = request.POST.get('new_run')
    #     old_run_schedule = license_obj.run_schedule
    #     if new_run_schedule != old_run_schedule:
    #         license_obj.run_schedule = new_run_schedule
    #         license_obj.save()
    #         tmp_file_name = "/tmp/" + str(uuid.uuid4())
    #
    #         if int(new_run_schedule) == 0:
    #             command = "/usr/bin/crontab -r"
    #             logging.info("User {u} set scheduler to not running".format(u=user_name))
    #         else:
    #
    #             # command = "/bin/echo 0 \*" + "/" + new_run_schedule + \
    #             #           " \* \* \* /home/checkit/camera_checker/main_menu/compare_images_v2.bin | crontab -"
    #             tmp_file = open(tmp_file_name, "w")
    #             tmp_file.write("0 */" + new_run_schedule +
    #                            " * * * /home/checkit/env/bin/python /home/checkit/camera_checker/main_menu/start.py \n")
    #             tmp_file.close()
    #             # command = "/bin/echo 0 *" + "/" + new_run_schedule + \
    #             #           " \* \* \* /home/checkit/env/bin/python " \
    #             #           "/home/checkit/camera_checker/main_menu/start.py | sudo -n crontab -u www-data "
    #             command = "crontab " + tmp_file_name
    #
    #         subprocess.Popen(command, shell=True)
    #         command = "rm " + tmp_file_name
    #         try:
    #             subprocess.Popen(command, shell=True)
    #         except:
    #             pass
    #         logging.info(f"User {user_name} modified run schedule to {new_run_schedule}"
    #                      f" hours from {old_run_schedule} hours")
    #     return HttpResponseRedirect(reverse(scheduler))
    if request.method == 'POST' and 'camera_check' in request.POST:
        input_number = request.POST.get('camera_check')
        try:
            camera_object = Camera.objects.get(camera_number=input_number)
        except ObjectDoesNotExist:
            obj = EngineState.objects.last()
            state = obj.state
            license_obj = Licensing.objects.last()
            run_schedule = license_obj.run_schedule
            context = {'camera_does_not_exist': input_number, 'system_state': state, 'run_schedule': run_schedule}
            return HttpResponse(template.render(context, request))
        camera_number = str(camera_object.camera_number)
        # process_output = subprocess.check_output(["/home/checkit/camera_checker/main_menu/compare_images_v2.bin",
        #                                           camera_number])
        # process_output = subprocess.check_output(["/home/checkit/env/bin/python",
        #                                           "/home/checkit/camera_checker/main_menu/start.py", camera_number])
        child_process = Popen(["/home/checkit/env/bin/python",
                              "/home/checkit/camera_checker/main_menu/start.py", camera_number],
                              stdout=PIPE, stderr=PIPE)
        stdout, stderr = child_process.communicate()
        return_code = child_process.returncode
        # print('return_code', return_code)
        # logging.info(f"views 619  {return_code}, {stdout}, {stderr}")
        if return_code == 33:
            pass
            context = {"error": "Licensing Error"}
            return HttpResponse(template.render(context, request))
        elif return_code == 0:
            logging.info(f"User {user_name} completed camera check for camera {camera_number}")
            process_output = "Run Completed - No errors reported"
            logging.info("Process Output {p}".format(p=process_output))
            return HttpResponseRedirect(reverse(index))
        else:
            logging.error("Error in camera check for camera {} - {}".format(camera_number, stderr))
            context = {"error": "Error Checking Camera"}
            return HttpResponse(template.render(context, request))
    return HttpResponse(template.render(context, request))


@login_required
def licensing(request):
    # user_name = request.user.usename
    # logging.info("User {u} access to Licensing".format(u=user_name))
    template = loader.get_template('main_menu/license.html')
    # get the actual state from the engine here and pass it to context
    obj = Licensing.objects.last()
    start_date = ""
    current_end_date = ""
    current_transaction_limit = ""
    current_transaction_count = ""
    license_owner = ""
    site_name = ""

    if obj:
        start_date = obj.start_date
        start_date = datetime.datetime.strftime(start_date, "%d-%B-%Y")
        current_end_date = obj.end_date
        current_end_date = datetime.datetime.strftime(current_end_date, "%d-%B-%Y")
        current_transaction_limit = obj.transaction_limit
        current_transaction_count = obj.transaction_count
        license_owner = obj.license_owner
        site_name = obj.site_name
    context = {'start_date': start_date, 'end_date': current_end_date, 'site_name': site_name,
               'transaction_limit': current_transaction_limit, 'license_owner': license_owner,
               'transaction_count': current_transaction_count}

    if request.method == 'POST' and 'download_license' in request.POST:
        machine_uuid, root_fs_uuid, product_uuid, encoded_string, mysql_password = get_license_details()
        response = HttpResponse(encoded_string, content_type="application/octet-stream")
        response['Content-Disposition'] = 'inline; filename=' + os.path.basename("license_details.bin")
        return response
    if request.FILES:
        uploaded_file = request.FILES['myfile'].read()
        f = Fernet(key)
        try:
            decrypted_file = f.decrypt(uploaded_file).decode()
        except InvalidToken:
            context['status'] = "ERROR: Invalid file"
            return HttpResponse(template.render(context, request))
        license_details = ast.literal_eval(decrypted_file)
        uploaded_end_date = license_details['end_date']
        uploaded_purchased_cameras = license_details['purchased_cameras']
        uploaded_purchased_transactions = license_details['purchased_transactions']
        uploaded_license_key = license_details['license_key']
        uploaded_machine_uuid = license_details['machine_uuid']
        uploaded_root_fs_uuid = license_details['root_fs_uuid']
        uploaded_product_uuid = license_details['product_uuid']
        uploaded_customer_name = license_details['customer_name']
        uploaded_site_name = license_details['site_name']
        machine_uuid, root_fs_uuid, product_uuid, encoded_string, mysql_password = get_license_details()
        if machine_uuid != uploaded_machine_uuid and root_fs_uuid != uploaded_root_fs_uuid \
                and product_uuid != uploaded_product_uuid:
            context['status'] = "ERROR: License details don't match"
            return HttpResponse(template.render(context, request))

        else:
            adm_db_config = {
                "host": "localhost",
                "user": "root",
                "password": mysql_password,
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
                    admin_cursor = adm_db.cursor()
                    if mysql_password:
                        sql_statement = f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{mysql_password}';"
                        admin_cursor.execute(sql_statement)
                        sql_statement = "FLUSH PRIVILEGES;"
                        admin_cursor.execute(sql_statement)
                        adm_db_config = {
                            "host": "localhost",
                            "user": "root",
                            "password": mysql_password,
                            "database": "adm"
                        }
                except mysql.connector.Error as e:
                    logging.info(f"Failed all attempts at accessing database {e}")

            try:
                admin_cursor = adm_db.cursor()

                # Need logic to check if license record exists - if it does then get prev tx_limit MINUS
                # the tx_count ( left over transactions ) and set tx_count = 0 - left over transactions
                sql_statement = "SELECT * from adm ORDER BY id DESC LIMIT 1"
                admin_cursor.execute(sql_statement)
                result = admin_cursor.fetchone()
                remaining_transactions = 0
                if result:
                    remaining_transactions = result[1] - result[2]
                    new_license_key = get_hash("{}{}{}{}".format(uploaded_purchased_transactions, uploaded_end_date,
                                               result[4], uploaded_purchased_cameras))
                    if new_license_key != uploaded_license_key:
                        logging.info(f"keys dont match  {new_license_key}, {uploaded_license_key}")
                        context['status'] = "ERROR: License keys mismatch"
                        return HttpResponse(template.render(context, request))
                else:
                    pass
                start_date = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d")
                sql_statement = """INSERT INTO adm (tx_count, tx_limit, end_date, license_key, camera_limit, 
                                   customer_name, site_name) VALUES (%s,%s,%s,%s,%s,%s,%s)"""
                values = (remaining_transactions, uploaded_purchased_transactions, uploaded_end_date,
                          uploaded_license_key, uploaded_purchased_cameras, uploaded_customer_name, uploaded_site_name)
                admin_cursor.execute(sql_statement, values)
                adm_db.commit()
                adm_db.close()

                license_record = Licensing(start_date=start_date, end_date=uploaded_end_date,
                                           transaction_limit=uploaded_purchased_transactions,
                                           transaction_count=remaining_transactions,
                                           license_key=uploaded_license_key,
                                           license_owner=uploaded_customer_name,
                                           site_name=uploaded_site_name,
                                           run_schedule=1)
                try:
                    license_record.save()
                except Exception as e:
                    logging.info(f"licensing error {e}")
                context['status'] = "SUCCESS: License details saved"
                return HttpResponse(template.render(context, request))
            except:
                context['status'] = "ERROR: Unable to save license details"
                return HttpResponse(template.render(context, request))

    return HttpResponse(template.render(context, request))


class CameraView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Camera
    table_class = CameraTable
    template_name = 'main_menu/camera_table.html'
    paginate_by = 18
    filterset_class = CameraFilter
    ordering = 'camera_number'


class CameraSelectView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Camera
    table_class = CameraSelectTable
    template_name = 'main_menu/camera_select_table.html'
    paginate_by = 100
    filterset_class = CameraSelectFilter
    ordering = 'camera_number'

class LogView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = LogImage
    table_class = LogTable
    template_name = 'main_menu/log_table.html'
    paginate_by = 18
    filterset_class = LogFilter
    ordering = '-creation_date'


def get_date(request):
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = DateForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            # ...
            # redirect to a new URL:

            return HttpResponse("value", form.cleaned_data)

    # if a GET (or any other method) we'll create a blank form
    else:
        form = RegionsForm()

    return render(request, 'main_menu/date.html', {'form': form})


class EngineStateView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = EngineState
    table_class = EngineStateTable
    template_name = 'main_menu/engine_state_table.html'
    paginate_by = 24
    filterset_class = EngineStateFilter
    ordering = 'state_timestamp'

    def get_queryset(self):
        # You can manipulate the QuerySet here to exclude records based on a condition
        queryset = super().get_queryset()  # Get the original QuerySet
        return queryset.exclude(state='STARTED')

# def engine_state_view(request):
#
#     records_to_display = EngineState.objects.exclude(state='STARTED')
#     table = EngineStateTable(records_to_display)
#     paginate_by = 24
#     filterset_class = EngineStateFilter
#     ordering = 'state_timestamp'
#
#     return render(request, "main_menu/engine_state_table.html", {
#         "table": table
#     })

def download_system_logs(request):
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="result_export.csv"'},
    )

def mass_update(request):
    selection = request.POST.getlist("selection")
    selection.sort()
    action = request.POST.get('action')
    matching_threshold = request.POST.get('matching_threshold')
    focus_threshold = request.POST.get('focus_threshold')
    light_threshold = request.POST.get('light_threshold')
    values = [selection, action,
              ",", matching_threshold,
              ",", focus_threshold,
              ",", light_threshold]
    if selection:
        for camera_number in selection:
            try:
                camera_object = Camera.objects.get(pk=camera_number)
                values.append(camera_object.camera_name)

                if matching_threshold:
                    camera_object.matching_threshold = matching_threshold
                if focus_threshold:
                    camera_object.focus_value_threshold = focus_threshold
                if light_threshold:
                    camera_object.light_level_threshold = light_threshold
                if action == "Reset Schedule":
                    all_days = DaysOfWeek.objects.all()
                    all_hours = HoursInDay.objects.all()
                    camera_object.scheduled_days.add(*all_days)
                    camera_object.scheduled_hours.add(*all_hours)
                camera_object.save()

            except ObjectDoesNotExist:
                values.append(f"Camera {camera_number} not found")

    return HttpResponse(values)

def export_logs_to_csv(request):
    selection = request.POST.getlist("selection")
    selection.sort()
    # print(selection)
    log_list = []
    if selection:
        for i in selection:
            current_record = EngineState.objects.get(id=i)
            # print(current_record)
            if EngineState.objects.get(id=i).state != "RUN COMPLETED":
                # selection.remove(i)
                continue
            else:
                try:
                    previous_record = current_record.get_previous_by_state_timestamp()
                    # print(previous_record.id, previous_record.state_timestamp)
                    start = previous_record.state_timestamp
                except ObjectDoesNotExist:
                    start = current_record.state_timestamp
                end = current_record.state_timestamp
                logs = LogImage.objects.filter(creation_date__range=(start, end))
                for log in logs:
                    log_list.append(log.id)
                    # print(log_list)
        # start = EngineState.objects.get(id=selection[0]).state_timestamp
        # end = EngineState.objects.get(id=selection[-1]).state_timestamp
        #
        # logs = LogImage.objects.filter(creation_date__range=(start, end))
        logs = LogImage.objects.filter(id__in=log_list)

        if request.POST.get('action') == "Export CSV":
            response = HttpResponse(
                content_type='text/csv',
                headers={'Content-Disposition': 'attachment; filename="result_export.csv"'},
            )

            writer = csv.writer(response)
            writer.writerow(["camera_name", "camera_number", "camera_location",
                             "pass_fail", "matching_score", "focus_value", "creation_date"])
            # print(logs)
            for log in logs:
                writer.writerow([log.url.camera_name, log.url.camera_number, log.url.camera_location,
                                 log.action, log.matching_score, log.focus_value,
                                 datetime.datetime.strftime(log.creation_date, "%d-%b-%Y %H:%M:%S")])

            return response

        elif request.POST.get('action') == "Export PDF":
            image_list = []
            log = []
            base_image = ""
            for log in logs:
                if log.action == "Failed":
                    camera_name = log.url.camera_name
                    camera_number = log.url.camera_number
                    hour = str(log.creation_date.hour).zfill(2)
                    log_image = settings.MEDIA_ROOT + "/" + str(log.image)
                    if not os.path.exists(log_image):
                        logging.error(f"missing logfile {log_image}")
                        continue
                    camera = Camera.objects.filter(id=log.url_id)
                    # print(camera)
                    for c in camera:
                        base_image = settings.MEDIA_ROOT + "/base_images/" + str(c.id) + "/" + hour + ".jpg"
                    if not os.path.exists(base_image):
                        logging.error(f"missing baseimage for logs {base_image}")
                        continue
                    matching_score = log.matching_score
                    focus_value = log.focus_value
                    light_level = log.light_level

                    image_list.append((camera_name, camera_number, log.creation_date, base_image, matching_score,
                                       focus_value, log_image, light_level))
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=landscape(A4))

            page_width, page_height = landscape(A4)
            if image_list:
                while len(image_list) > 0:
                    left_margin_pos = 20
                    top_margin_text_pos = 23
                    top_margin_image_pos = 67
                    second_image_pos = 85
                    count = 0
                    c.setFillColor(HexColor("#a2a391"))
                    c.setStrokeColor(HexColor("#a2a391"))

                    c.rect(0, 0, page_width, page_height, stroke=1, fill=1)
                    # this creates a rectangle the size of the sheet
                    c.setFillColor(HexColor("#000000"))
                    c.setStrokeColor(HexColor("#000000"))

                    c.setFont("Helvetica-BoldOblique", 18, )
                    c.drawString(*coord(110, 10, page_height, mm), text="Failed Images Report")

                    c.setFont("Helvetica", 10)
                    c.drawString(*coord(270, 10, page_height, mm), text="Page " + str(c.getPageNumber()))
                    for i in image_list[:3]:
                        camera_name, camera_number, creation_time, base_image, matching_score, focus_value, log_image, light_level = i

                        c.drawString(
                            *coord(left_margin_pos, top_margin_text_pos + (count * top_margin_image_pos) - 5,
                                   page_height, mm), text="Camera Name: " + camera_name)
                        c.drawString(
                            *coord(left_margin_pos + 88, top_margin_text_pos + (count * top_margin_image_pos) - 5,
                                   page_height, mm), text="Camera Number: " + str(camera_number))
                        c.drawString(*coord(left_margin_pos, top_margin_text_pos + (count * top_margin_image_pos),
                                            page_height, mm),
                                     text="Capture: " + creation_time.strftime("%d-%b-%Y %H:%M %p"))
                        c.drawString(*coord(left_margin_pos + 88, top_margin_text_pos + (count * top_margin_image_pos),
                                            page_height, mm), text="Matching Score: " + str(matching_score) +
                                                                   "            Focus Value: " + str(focus_value))
                        c.drawString(*coord(left_margin_pos + 177, top_margin_text_pos + (count * top_margin_image_pos),
                                            page_height, mm), text="Light Level: " + str(light_level))

                        image_rl = canvas.ImageReader(base_image)
                        image_width, image_height = image_rl.getSize()
                        scaling_factor = (image_width / page_width) * 1.3
                        if image_height > 1920:
                            sf_multiplier = 2.311/(image_width/image_height)
                            scaling_factor = (image_width / page_width) * sf_multiplier
                        c.setLineWidth(2)
                        c.setStrokeColor(HexColor("#b9b6a9"))
                        c.roundRect(left_margin_pos + 11,
                                    page_height - (top_margin_image_pos + (count * top_margin_image_pos * mm)) - 139,
                                    width=773, height=168, radius=4, stroke=1, fill=0)
                        c.setStrokeColor(HexColor("#767368"))
                        c.roundRect(left_margin_pos + 10,
                                    page_height - (top_margin_image_pos + (count * top_margin_image_pos * mm)) - 140,
                                    width=775, height=170, radius=4, stroke=1, fill=0)
                        c.drawImage(image_rl,
                                    *coord(left_margin_pos - 2,
                                           top_margin_image_pos + (count * top_margin_image_pos) + 3,
                                           page_height, mm),
                                    width=image_width / (mm * scaling_factor),
                                    height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)
                        image_rl2 = canvas.ImageReader(log_image)
                        image_width, image_height = image_rl.getSize()

                        c.drawImage(image_rl2,
                                    *coord(left_margin_pos + 2 + second_image_pos,
                                           top_margin_image_pos + (count * top_margin_image_pos) + 3,
                                           page_height, mm), width=image_width / (mm * scaling_factor),
                                    height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)
                        log_image_cv2 = cv2.imread(log_image)
                        log_image_edges = get_transparent_edge(log_image_cv2, (0, 0, 255))
                        log_image_edges = log_image_edges[:, :, :3]
                        reference_image_cv2 = cv2.imread(base_image)
                        merged_image = cv2.addWeighted(reference_image_cv2, 1, log_image_edges, 1, 0)
                        cv2.imwrite("/tmp/merged_image.jpg", merged_image)
                        image_rl3 = canvas.ImageReader("/tmp/merged_image.jpg")

                        c.drawImage(image_rl3,
                                    *coord(left_margin_pos + 2 + (2 * second_image_pos) + 5,
                                           top_margin_image_pos + (count * top_margin_image_pos) + 3,
                                           page_height, mm), width=image_width / (mm * scaling_factor),
                                    height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)

                        count += 1
                    c.showPage()
                    del image_list[:3]
                c.save()
                buffer.seek(0)

                return FileResponse(buffer, as_attachment=True, filename='results.pdf')
            else:
                c.setFillColor(HexColor("#a2a391"))
                c.setStrokeColor(HexColor("#a2a391"))
                path = c.beginPath()
                path.moveTo(0 * cm, 0 * cm)
                path.lineTo(0 * cm, 30 * cm)
                path.lineTo(25 * cm, 30 * cm)
                path.lineTo(25 * cm, 0 * cm)
                # this creates a rectangle the size of the sheet
                c.drawPath(path, True, True)
                c.setFillColor(HexColor("#000000"))
                c.setStrokeColor(HexColor("#000000"))
                c.setFont("Helvetica-BoldOblique", 18, )
                c.drawString(*coord(25, 10, page_height, mm),
                             text="There are no failed images for the selected records")
                c.showPage()
                c.save()
                buffer.seek(0)
                return FileResponse(buffer, as_attachment=True, filename='results.pdf')

    else:
        return HttpResponseRedirect("/state/")


@permission_required('camera_checker.main_menu')
def input_camera_for_regions(request):
    user_name = request.user.username
    logging.info("User {u} access to Regions".format(u=user_name))

    if request.method == 'POST':

        try:
            camera_number = request.POST.get('camera_number')
            camera_object = Camera.objects.get(camera_number=camera_number)

            regions = camera_object.image_regions
            if regions == "":
                regions = "[]"

        except ObjectDoesNotExist:
            message = "Camera does not exist"
            return render(request, 'main_menu/regions.html', {'message': message})

        initial_data = {'regions': eval(regions)}
        form = RegionsForm(initial=initial_data)

        url_id = camera_object.id
        reference_images = ReferenceImage.objects.filter(url_id=url_id)
        if reference_images:
            base64_image = get_base_image(reference_images, url_id, regions)
            try:
                log_obj = LogImage.objects.filter(url_id=url_id).last()
                if not log_obj:
                    raise ObjectDoesNotExist
                else:
                    region_scores = log_obj.region_scores
                    if not isinstance(region_scores, dict):
                        region_scores = {}
                    creation_date = log_obj.creation_date
                    regions = []
                    scores = []
                    for k, v in region_scores.items():
                        regions.append(int(k))
                        scores.append(v)
                    sorted_regions = sorted(region_scores, key=region_scores.get)
                    low_regions = sorted_regions[:8]
                    for i in range(0, len(low_regions)):
                        low_regions[i] = int(low_regions[i])
                    high_regions = sorted_regions[-8:]
                    for i in range(0, len(high_regions)):
                        high_regions[i] = int(high_regions[i])
                    scores_field = {'regions': [regions], 'scores': [scores], 'low_regions': low_regions,
                                    'high_regions': high_regions}
            except ObjectDoesNotExist:
                scores_field = {}
                creation_date = ""

            context = {
                'form': form,
                'camera_number': camera_number,
                'image': base64_image,
                'scores_field': scores_field,
                'creation_date': creation_date
            }
            return render(request, 'main_menu/regions_main_form.html', context=context)
        else:
            message = "No reference images for this camera"
            return render(request, 'main_menu/regions.html', {'message': message})
    else:
        message = ""
        return render(request, 'main_menu/regions.html', {'message': message})


@permission_required('camera_checker.main_menu')
def display_regions(request):
    if request.method == "POST":
        form = RegionsForm(request.POST)

        if form.is_valid() and 'reset' in request.POST:
            regions = '[]'
        else:
            regions = str(form.cleaned_data['regions'])

        camera_number = request.POST.get('camera_number')
        camera_object = Camera.objects.get(camera_number=camera_number)
        camera_object.image_regions = regions
        camera_object.save()

        initial_data = {'regions': eval(regions)}
        form = RegionsForm(initial=initial_data)

        url_id = camera_object.id
        reference_images = ReferenceImage.objects.filter(url_id=camera_object.id)
        if reference_images:
            base64_image = get_base_image(reference_images, url_id, regions)
            try:
                log_obj = LogImage.objects.filter(url_id=url_id).last()
                if not log_obj:
                    raise ObjectDoesNotExist
                else:
                    region_scores = log_obj.region_scores
                    creation_date = log_obj.creation_date
                    regions = []
                    scores = []
                    for k, v in region_scores.items():
                        regions.append(int(k))
                        scores.append(v)
                    sorted_regions = sorted(region_scores, key=region_scores.get)
                    low_regions = sorted_regions[:8]
                    for i in range(0, len(low_regions)):
                        low_regions[i] = int(low_regions[i])
                    high_regions = sorted_regions[-8:]
                    for i in range(0, len(high_regions)):
                        high_regions[i] = int(high_regions[i])
                    scores_field = {'regions': [regions], 'scores': [scores], 'low_regions': low_regions,
                                    'high_regions': high_regions}
            except ObjectDoesNotExist:
                scores_field = {}
                creation_date = ""

            context = {
                'form': form,
                'camera_number': camera_number,
                'image': base64_image,
                'scores_field': scores_field,
                'creation_date': creation_date
            }
            return render(request, 'main_menu/regions_main_form.html', context=context)

    else:
        message = ""
        return render(request, 'main_menu/regions.html', {'message': message})


