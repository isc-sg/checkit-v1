import ast
import datetime
import pytz
from datetime import timedelta
import subprocess
import time
import zipfile
import tarfile
from decimal import Decimal
from io import BytesIO
from subprocess import PIPE, Popen
import csv
import os
import shutil
import io
import base64
import logging
from logging.handlers import RotatingFileHandler
from bisect import bisect_left
from unicodedata import decimal

import cv2
import numpy as np
import uuid
import mysql.connector
import psutil
from celery.utils.functional import pass1
from django.contrib.admin.templatetags.admin_list import pagination
from django.core.serializers import serialize
from django.utils import timezone
from django.db.models.functions import TruncHour
from django.db.models import Count
from pathos.multiprocessing import cpu_count
import configparser
from collections import defaultdict
from itertools import islice



from django.http import HttpResponse, HttpResponseRedirect, FileResponse, Http404, JsonResponse
from django.template import loader
from django.shortcuts import render, reverse, redirect
from tablib import Dataset
from django_tables2 import SingleTableMixin, SingleTableView, LazyPaginator
from django_filters.views import FilterView
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.views.decorators.cache import cache_control
from django.contrib.auth.models import Permission, User, Group
from django.core.paginator import Paginator
from rest_framework.renderers import JSONRenderer
from rest_framework.pagination import PageNumberPagination


from .resources import CameraResource
from .models import EngineState, Camera, LogImage, Licensing, ReferenceImage, DaysOfWeek, HoursInDay, SuggestedValues
from .tables import (CameraTable, LogTable, EngineStateTable, CameraSelectTable,
                     LogSummaryTable, SuggestedValuesTable, ReferenceImageTable)
from .forms import DateForm, RegionsForm, FilterForm
from .filters import CameraFilter, LogFilter, EngineStateFilter, CameraSelectFilter, ReferenceImageFilter
import main_menu.select_region as select_region
from django.contrib.admin.models import LogEntry
from django.contrib.auth.decorators import user_passes_test


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
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView, ListAPIView, ListCreateAPIView, RetrieveDestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample

import importlib

from main_menu.tasks import process_cameras, find_best_regions

from main_menu.serializers import (CameraSerializer, LogImageSerializer,
                                   ReferenceImageSerializer)

from celery import Celery, current_app
import celery
from celery import shared_task, group
from celery.result import AsyncResult, GroupResult
from celery.exceptions import *

from rest_framework.views import APIView
from rest_framework.response import Response
from .scheduler_task_manager import CeleryTaskManager
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.http import StreamingHttpResponse
from django.db import models
from decimal import Decimal, ROUND_HALF_UP



__version__ = 2.11

# import main_menu.compare_images_v4

# logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
#                                                '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
#                     handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
#                                                   maxBytes=10000000, backupCount=10)])
logger = logging.getLogger(__name__)
error_image = np.zeros((720, 1280, 3), np.uint8)

error_image = cv2.putText(error_image, "Error retrieving image",
                          (250, 300), cv2.FONT_HERSHEY_TRIPLEX, 2,
                          (0, 0, 255), 2, cv2.LINE_AA)


def array_to_string(array):
    new_string = ""
    for element in array:
        new_string += chr(element)
    return new_string


# checkit_secret = "Checkit65911760424"[::-1].encode()
# convert strings to ascii decimal values as an array - this helps obfuscate the string after compiling
checkit_array = [52, 50, 52, 48, 54, 55, 49, 49, 57, 53, 54, 116, 105, 107, 99, 101, 104, 67]

checkit_secret = array_to_string(checkit_array).encode()

# key = b'Bu-VMdySIPreNgve8w_FU0Y-LHNvygKlHiwPlJNOr6M='

key_array = [66, 117, 45, 86, 77, 100, 121, 83, 73, 80, 114, 101, 78, 103, 118, 101, 56, 119, 95, 70, 85, 48, 89, 45,
             76, 72, 78, 118, 121, 103, 75, 108, 72, 105, 119, 80, 108, 74, 78, 79, 114, 54, 77, 61]

key = array_to_string(key_array).encode()

number_of_cpus = cpu_count()
socket_timeout = 1
CHECKIT_HOST = ""
HOST = ""
PORT = 0
network_interface = ""
log_alarms = False
mysql_password = None
log_retention_period_days = 30

def get_config():
    config = configparser.ConfigParser()
    config.read('/home/checkit/camera_checker/main_menu/config/config.cfg')
    global CHECKIT_HOST
    global HOST
    global PORT
    global network_interface
    global log_alarms
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

        CHECKIT_HOST = config['DEFAULT']['checkit_host']
    except configparser.NoOptionError:
        logger.error("Unable to read config file")

        if config.has_option('DEFAULT', 'log_retention_period_days',):
            try:
                PORT = config.getint('DEFAULT', 'log_retention_period_days', fallback=30)
            except ValueError:
                logger.error("Please check config file for log_retention_period_days")

#
# class UserViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint that allows users to be viewed or edited.
#     """
#     queryset = User.objects.all().order_by('-date_joined')
#     serializer_class = UserSerializer
#     permission_classes = [permissions.IsAuthenticated]

def group_required(group_name):
    def in_group(user):
        return user.is_authenticated and user.groups.filter(name=group_name).exists()

    return user_passes_test(in_group)


def chunk_list(lst, number_of_groups):
    # Calculate the size of each chunk
    chunk_length = len(lst) // number_of_groups
    remainder = len(lst) % number_of_groups

    # Create the groups
    chunks = []
    start = 0
    for i in range(number_of_groups):
        # Distribute the remainder evenly across the first groups
        end = start + chunk_length + (1 if i < remainder else 0)
        chunks.append(lst[start:end])
        start = end

    return chunks


def group_cameras_by_psn_ip(camera_list=None):
    # Fetch all Camera objects from the database
    if isinstance(camera_list, list):
        cameras = Camera.objects.filter(id__in=camera_list)
    else:
        cameras = Camera.objects.all()
    # Initialize defaultdict to group cameras by psn_ip_address
    grouped = defaultdict(list)

    # Group cameras by psn_ip_address
    for camera in cameras:
        psn_ip = camera.psn_ip_address
        grouped[psn_ip].append(camera.id)

    if None in grouped:
        original_list = grouped[None]
        app = celery.Celery('camera_checker', broker='redis://localhost:6379')
        # active_workers = app.control.inspect().ping()
        inspect = app.control.inspect()
        stats = inspect.stats()
        total_concurrency = 0
        if stats:
            for worker, worker_stats in stats.items():
                concurrency = worker_stats.get('pool', {}).get('max-concurrency', 'N/A')
                total_concurrency += concurrency
        # Now split the Non_psn cameras into sublists of total_concurrency
        split_lists = chunk_list(original_list, number_of_groups=total_concurrency)
        grouped[None] = split_lists
        flattened_lists = []

        for value in grouped.values():
            if isinstance(value[0], list):  # Check if the first element is a list
                flattened_lists.extend(value)  # Extend the list with the lists inside the list
            else:
                flattened_lists.append(value)
    else:
        flattened_lists = list(grouped.values())
    return flattened_lists


def split_list(input_list, num_lists):
    avg_size = len(input_list) // num_lists
    remainder = len(input_list) % num_lists

    result = []
    start = 0

    for i in range(num_lists):
        end = start + avg_size + (1 if i < remainder else 0)
        result.append(input_list[start:end])
        start = end

    return result


def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).
    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))

class CheckSoftwareVersionsView(APIView):
    permission_classes = [IsAuthenticated]


    def get(self, request):
        directory = "/home/checkit/camera_checker/main_menu/"
        software_files = files = os.listdir(directory)
        try:
            # List all files in the directory
            version_dict = {}
            files = os.listdir(directory)
            version_ascii_array = [95, 95, 118, 101, 114, 115, 105, 111, 110, 95, 95]
            for file in files:
                # Check if the file is a .so or .py file
                file_path = os.path.join(directory, file)
                if file.endswith('.so'):
                    module_name = file.split(".")[0]
                    module = importlib.import_module("main_menu." + module_name)
                    version = getattr(module, array_to_string(version_ascii_array), "Version not found")
                    version_dict[file] = str(version)
                elif file.endswith('.py'):

                    result = subprocess.run(['grep', array_to_string(version_ascii_array), f"{directory}{file}"], capture_output=True, text=True)
                    if result.returncode == 0:
                        # Extract version from the output
                        for line in result.stdout.splitlines():
                            parts = line.split('=')
                            if len(parts) > 1:
                                version = parts[1].strip().strip('"').strip("'")
                                version_dict[file] = str(version)
                    else:
                        version_dict[file] = "Version not found"
                else:
                    continue  # Skip files that are neither .so nor .py
            sorted_version_dict = dict(sorted(version_dict.items()))
            return Response(sorted_version_dict)

        except Exception as e:
            print(f"An error occurred: {e}")

class ActiveTasksView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="listActiveSchedulerTasks",
        description="Retrieve all currently active tasks in the scheduler.",
        tags=["scheduler"],
        responses={
            200: openapi.Response(
                description="List of active tasks in the scheduler.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "tasks": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "id": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description="Unique task ID."
                                    ),
                                    "name": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description="Name of the method called."
                                    ),
                                    "args": openapi.Schema(
                                        type=openapi.TYPE_ARRAY,
                                        items=openapi.Schema(type=openapi.TYPE_STRING),
                                        description="Arguments passed to the task."
                                    ),
                                    "kwargs": openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        additional_properties=openapi.Schema(
                                            type=openapi.TYPE_STRING
                                        ),
                                        description="Keyword arguments passed to the task."
                                    ),
                                    "worker": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description="Name of the worker executing the task."
                                    ),
                                },
                            ),
                            description="List of active tasks.",
                        )
                    },
                    example={
                        "tasks": [
                            {
                                "id": "unique_id",
                                "name": "called_from_method",
                                "args": ["status_of_submission", "list_of_cameras", "run_number", "user"],
                                "kwargs": {"key": "value"},
                                "worker": "worker_name",
                            }
                        ]
                    }
                )
            )
        }
    )
    def get(self, request):
        task_manager = CeleryTaskManager()
        tasks = task_manager.get_active_tasks()
        return Response({'tasks': tasks})

class Test500ErrorView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        raise Exception()

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10  # Number of items per page
    page_size_query_param = 'page_size'  # Allows clients to override the page size
    max_page_size = 100  # Maximum limit allowed when overridden

class CheckCamerasView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="CheckCameras",
        operation_description="Execute a check on a given list of cameras",
        tags=["check_camera"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'camera_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,  # Specify it as an array
                    items=openapi.Items(type=openapi.TYPE_INTEGER),  # Array items are integers
                    description="List of camera IDs to check",
                ),
                'force_check': openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,  # Specify it as a boolean
                    description="Force the check to execute regardless of conditions",
                )
            },
            required=['camera_ids']
        ),
        responses={  # Place this outside the `request_body` definition
            200: openapi.Response(description="Cameras check initiated"),
            400: openapi.Response(description="Invalid input"),
        }
    )
    def post(self, request):

        camera_ids = request.data.get('camera_ids')

        if not camera_ids:
            return Response(
                {"error": "camera_ids is required and must be a list of integers."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if isinstance(camera_ids, list):
            try:
                if not all(isinstance(part,int) for part in camera_ids):
                    raise ValueError("Non-integer value found")
            except ValueError:
                return Response(
                    {"error": "camera_ids must contain only integers"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif isinstance(camera_ids, str):
            try:
                # Split the string by commas
                parts = camera_ids.split(",")

                # Ensure all parts are digits before converting
                if not all(part.strip().isdigit() for part in parts):
                    raise ValueError("Non-integer value found")

                # Convert all parts to integers
                camera_ids = [int(part.strip()) for part in parts]
            except ValueError:
                return Response(
                    {"error": "camera_ids must contain only integers separated by commas."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {"error": "camera_ids must be a string of integers separated by commas."},
                status=status.HTTP_400_BAD_REQUEST
            )


        existing_ids = set(Camera.objects.filter(id__in=camera_ids).values_list('id', flat=True))
        input_ids = set(camera_ids)
        missing_ids = input_ids - existing_ids

        if missing_ids:
            return Response(
                {"error": f"The list contains invalid camera ids {missing_ids}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_name = request.user.username
        if request.data.get('force_check'):
            force_check = request.data.get('force_check')
        else:
            force_check = False
        number_of_cameras_in_run = len(camera_ids)
        engine_state_record = EngineState(state="STARTED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_id = engine_state_record.id
        process_cameras.delay([camera_ids], engine_state_id, user_name, force_check=force_check)

        return Response(
            {"message": "Camera check tasks have been initiated.", "camera_ids": camera_ids, "engine_state_id": engine_state_id},
            status=status.HTTP_200_OK
        )


class CameraViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows cameras to be viewed or edited.
    """
    queryset = Camera.objects.all().order_by('camera_number')
    serializer_class = CameraSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'camera_number'

    @extend_schema(
        summary="Update the snooze status of a camera",
        description=(
            "Updates the snooze status of a camera. This method accepts a POST request with a form-body containing "
            "the 'snooze' field. The value for 'snooze' can be 'true', 'false', 'Yes', or 'No'. It updates the `snooze` "
            "attribute of the specified camera and returns a success response."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "snooze": {"type": "string", "description": "Snooze status ('true', 'false', 'Yes', or 'No')"}
                },
                "required": ["snooze"]
            }
        },
        responses={
            201: OpenApiResponse(
                description="Success",
                response={"type": "object", "properties": {"status": {"type": "string"}}},
                examples=[
                    OpenApiExample(
                        name="Success Example",
                        value={"status": "success"}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Bad request",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "error": {"type": "string"}
                    }
                },
                examples=[
                    OpenApiExample(
                        name="Missing Snooze Field Example",
                        value={"status": "fail", "error": "requires snooze field"}
                    ),
                    OpenApiExample(
                        name="Invalid Snooze Value Example",
                        value={"status": "fail", "error": "invalid value for snooze"}
                    )
                ]
            )
        },
    )

    @action(detail=True, methods=['post'])
    def snooze(self, request, camera_number=None):
        """
        
        Updates the snooze status of a camera.

        This method accepts a POST request with a form-body containing the 'snooze' field.
        The value for 'snooze' can be 'true', 'false', 'Yes', or 'No'.
        It updates the `snooze` attribute of the specified camera and returns a success response.

        Parameters:
        - request: The HTTP request object.
        - camera_number: The identifier of the camera to update.

        Returns:
        - JsonResponse with status "success" if the operation is successful.
        - JsonResponse with status "fail" and an error message if the 'snooze' field is missing or invalid.
        
        Must contain snooze in form-body and be true or false type.
        Values such as Yes or No also accepted
        """
        instance = self.get_object()

        camera_id = [instance.id]
        snooze: str = request.data.get('snooze')
        # print('camera_id', camera_id, snooze, camera_number)
        if not snooze:
            return JsonResponse({"status": "fail", "error": "requires snooze field"},
                                status=status.HTTP_400_BAD_REQUEST)

        try:
            new_value = strtobool(snooze)
        except ValueError:
            return JsonResponse({"status": "fail", "error": "invalid value for snooze"},
                                status=status.HTTP_400_BAD_REQUEST)

        instance.snooze = new_value
        instance.save()
        return JsonResponse({"status": "success"}, status=status.HTTP_201_CREATED)

    @extend_schema(
    summary="Enable/disable a camera",
    description=(
            "Toggles the disabled state of a camera. Accepts a POST body with 'disable' as a boolean-like string "
            "('true'|'false'|'yes'|'no'). When disabling (true), 'reason' is required. "
            "When enabling (false), any provided reason is ignored and cleared. "
            "The model auto-stamps/clears the disabled date."
        ),
    request={
            "application/json": {
                "type": "object",
                "properties": {
                    "disable": {"type": "string", "description": "Disable flag ('true'|'false'|'yes'|'no')"},
                    "disable_reason": {"type": "string", "description": "Required when disable is true"}
                },
                "required": ["disable"]
            }
        },
    responses={
            201: OpenApiResponse(
                description="Success",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "disabled": {"type": "boolean"},
                        "disable_reason": {"type": "string", "nullable": True},
                        "camera_disabled_date": {"type": "string", "format": "date-time", "nullable": True}
                    }
                },
                examples=[
                    OpenApiExample(
                        name="Disabled",
                        value={
                            "status": "success",
                            "disabled": True,
                            "disable_reason": "Lens damaged",
                        }
                    ),
                    OpenApiExample(
                        name="Enabled (re-enabled)",
                        value={
                            "status": "success",
                            "disabled": False,
                            "disable_reason": None,
                            "camera_disabled_date": None
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Bad request",
                response={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "error": {"type": "string"}
                    }
                },
                examples=[
                    OpenApiExample(
                        name="Missing Disable Field",
                        value={"status": "fail", "error": "requires disable field"}
                    ),
                    OpenApiExample(
                        name="Invalid Disable Value",
                        value={"status": "fail", "error": "invalid value for disable"}
                    ),
                    OpenApiExample(
                        name="Missing disable reason When Disabling",
                        value={"status": "fail", "error": "reason is required when disabling"}
                    )
                ]
            )
        },
    )
    @action(detail=True, methods=['post'])
    def disable(self, request, camera_number=None):
        """
        Toggle the camera's disabled state.

        Body:
            {
              "disable": "true" | "false" | "yes" | "no",
              "reason": "text (required when disabling)"
            }
        """
        instance = self.get_object()

        disable_raw = request.data.get('disable')
        if disable_raw is None:
            return JsonResponse({"status": "fail", "error": "requires disable field"},
                                status=status.HTTP_400_BAD_REQUEST)

        try:
            disable_flag = bool(strtobool(str(disable_raw)))
        except ValueError:
            return JsonResponse({"status": "fail", "error": "invalid value for disable"},
                                status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('disable_reason')

        if disable_flag:
            if not (reason and str(reason).strip()):
                return JsonResponse({"status": "fail", "error": "reason is required when disabling"},
                                    status=status.HTTP_400_BAD_REQUEST)
            instance.disable = True
            instance.disable_reason = reason.strip()
            # The model/serializer stamps date; stamp here too if empty for direct updates
            if instance.camera_disabled_date is None:
                instance.camera_disabled_date = timezone.now()
        else:
            # Re-enable: clear reason and date
            instance.disable = False
            instance.disable_reason = None
            instance.camera_disabled_date = None

        instance.save()

        return JsonResponse({
            "status": "success",
            "disabled": instance.disable,
            "disable_reason": instance.disable_reason,
            "camera_disabled_date": (
                instance.camera_disabled_date.isoformat() if instance.camera_disabled_date else None
            )
        }, status=status.HTTP_201_CREATED)


    
    @action(detail=True, methods=['post'])
    def refresh_reference_image(self, request, camera_number=None):
        """       
        Initiates a reference image refresh for a specified camera.

        This method accepts a POST request and starts the process to check the camera.
        If the reference image was previously deleted, it will create a new one.
        The checks are governed by schedule and only occur at the current hour according to the schedule.

        Parameters:
        - request: The HTTP request object.
        - camera_number: The identifier of the camera to refresh.

        Returns:
        - Response with a success message indicating that the refresh has been submitted.
        
        """
        instance = self.get_object()

        user_name = request.user.username

        camera_id = [instance.id]

        number_of_cameras_in_run = 1
        engine_state_record = EngineState(state="STARTED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_id = engine_state_record.id
        process_cameras(camera_id, engine_state_id, user_name, force_check=False)
        logger.info(f"API request completed refresh for camera {instance.camera_number}")
        return Response({'message': 'Camera refresh submitted.'})



class LogImageViewSet(APIView):
    """
    API endpoint that allows logs to be viewed. Use Run Number or Action to filter results.
    """
    # queryset = LogImage.objects.all().order_by('creation_date')
    # serializer_class = LogImageSerializer
    permission_classes = [IsAuthenticated]
    # lookup_field = 'id'
    # http_method_names = ['GET', 'delete']
    renderer_classes = [JSONRenderer]

    # Apply the pagination class (you can use a custom one if defined, otherwise use the default)
    pagination_class = StandardResultsSetPagination  # Use PageNumberPagination if you didn't define a custom one

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('run_number', openapi.IN_QUERY, description="Run Number", type=openapi.TYPE_STRING),
            openapi.Parameter('camera_number', openapi.IN_QUERY, description="Camera Number", type=openapi.TYPE_STRING),
            openapi.Parameter('from_creation_date', openapi.IN_QUERY, description="From creation date for searching", type=openapi.TYPE_STRING),
            openapi.Parameter('to_creation_date', openapi.IN_QUERY, description="To creation date for searching", type=openapi.TYPE_STRING),
            openapi.Parameter('action', openapi.IN_QUERY, description="Action", type=openapi.TYPE_STRING),
            openapi.Parameter('page', openapi.IN_QUERY, description="Page number", type=openapi.TYPE_INTEGER),
            openapi.Parameter('page_size', openapi.IN_QUERY, description="Number of items per page",
                              type=openapi.TYPE_INTEGER)

        ],
        responses={
            200: LogImageSerializer(many=True),
        }
    )


    def get(self, request):

        run_number = request.GET.get('run_number') or request.data.get('run_number')
        camera_number = request.GET.get('camera_number') or request.data.get('camera_number')
        action = request.GET.get('action') or request.data.get('action')
        from_creation_date = request.GET.get('from_creation_date') or request.data.get('from_creation_date')
        to_creation_date = request.GET.get('to_creation_date') or request.data.get('to_creation_date')

        queryset = LogImage.objects.all()
        if run_number:
            queryset = queryset.filter(run_number=run_number)
        if camera_number:
            queryset = queryset.filter(url__camera_number=camera_number)
        if action:
            queryset = queryset.filter(action=action)
        if from_creation_date and to_creation_date:
            try:
                from_creation_date = datetime.datetime.fromisoformat(from_creation_date.replace("Z", "+00:00")).date()
                to_creation_date = datetime.datetime.fromisoformat(to_creation_date.replace("Z", "+00:00")).date()
                queryset = queryset.filter(creation_date__range=(from_creation_date, to_creation_date))
            except Exception:
                return Response("Invalid dates")

        # Force ordering for stable pagination
        queryset = queryset.order_by('-creation_date')

        # Paginate (auto-handles page_size/page from request.GET)
        paginator = self.pagination_class()
        paginated_data = paginator.paginate_queryset(queryset, request)

        serializer = LogImageSerializer(paginated_data, many=True)
        return paginator.get_paginated_response(serializer.data)

class ReferenceImageListCreateAPIView(ListAPIView):
    """
    API endpoint that allows reference to be viewed or deleted only.
    """

    # def get_queryset(self):
    #     url = self.kwargs['url']
    #     return ReferenceImage.objects.filter(url=url)
    # def get_queryset(self):
    #     """
    #     Optionally restricts the returned purchases to a given user,
    #     by filtering against a `username` query parameter in the URL.
    #     """
    #     queryset = ReferenceImage.objects.all()
    #     url = self.request.query_params.get('url')
    #     if url is not None:
    #         queryset = queryset.filter(url_id=url)
    #     return queryset
    serializer_class = ReferenceImageSerializer

    def get_queryset(self):
        queryset = ReferenceImage.objects.all()
        camera_number = self.request.query_params.get('camera_number', None)
        if camera_number:
            queryset = queryset.filter(url__camera_number=camera_number)
        return queryset
    # model = ReferenceImage
    # queryset = ReferenceImage.objects.all().order_by('url__camera_number')
    # queryset = ReferenceImage.objects.all()
    # permission_classes = [permissions.IsAuthenticated]
    # lookup_field = 'url'
    # http_method_names = ['get', 'delete', 'post']
    # http_method_names = ['get', 'delete']


class ReferenceImagesDetailAPIView(RetrieveDestroyAPIView):
    queryset = ReferenceImage.objects.all()
    serializer_class = ReferenceImageSerializer

def is_process_running(pid):
    try:
        process = psutil.Process(pid)
        return process.is_running()
    except psutil.NoSuchProcess:
        return False


def custom_500_error_view(request):
    return render(request, '500.html')


def reference_image_api(request):
    session_id = request.session
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
            user_name = request.user.username
            session_id = request.session
            # child_process = Popen(["/home/checkit/env/bin/python",
            #                        "/home/checkit/camera_checker/main_menu/start.py", camera_number],
            #                       stdout=PIPE, stderr=PIPE)
            # stdout, stderr = child_process.communicate()
            # return_code = child_process.returncode
            # # print('return_code', return_code)
            # if return_code == 33:
            #     return HttpResponse("Error: Licensing Error")
            # elif return_code == 0:
            #     logger.info(f"API request completed camera check for camera {camera_number}")
            #     process_output = "Run Completed - No errors reported"
            #     logger.info("Process Output {p}".format(p=process_output))
            #     return HttpResponse(process_output)
            # else:
            #     logger.error("Error in camera check for camera {} - {}".format(camera_number, stderr))
            #     return HttpResponse("Error in camera check for camera {} - {}".format(camera_number, stderr))

            camera_number = str(camera_object.camera_number)
            camera_id = [camera_object.id]

            # state_timestamp = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d %H:%M:%S.%f")
            state_timestamp = timezone.now()
            number_of_cameras_in_run = 1
            engine_state_record = EngineState(state="STARTED", state_timestamp=state_timestamp, user=user_name,
                                              number_of_cameras_in_run=number_of_cameras_in_run)
            engine_state_record.save()
            engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=state_timestamp, user=user_name,
                                              number_of_cameras_in_run=number_of_cameras_in_run)
            engine_state_record.save()
            engine_state_id = engine_state_record.id
            process_cameras(camera_id, engine_state_id, user_name, force_check=False)
            logger.info(f"API request completed camera check for camera {camera_number}")
            return HttpResponse("Run Completed - No errors reported")

        elif action.lower() == "delete":
            if "hour" not in request.POST:
                return HttpResponse("Error: please provide hour for delete action")
            else:
                hour = request.POST['hour']
                # look up reference image and make sure it exists.
                # this currently can only delete the version set in camera - will need to
                # add version as a key to enable deleting earlier versions.
                # if we are a part way through a version change then it will not delete the latest version.
                try:
                    reference_image_object = ReferenceImage.objects.get(url_id=camera_object.id, hour=hour,
                                                                        version=camera_object.reference_image_version)
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


# class SnoozeCamera(GenericAPIView):
#     permission_classes = [AllowAny]
#     serializer_class = SnoozeCameraSerializer
#
#     def get(self, request):
#         """
#         API endpoint to get snooze value - must contain snooze in form-data.
#         """
#         if 'camera_number' in request.data:
#             camera_number = request.data['camera_number']
#         else:
#             return JsonResponse({"status": "fail", "error": "camera_number required for GET"},
#                                 status=status.HTTP_400_BAD_REQUEST)
#         try:
#             camera_object = Camera.objects.get(camera_number=camera_number)
#         except ObjectDoesNotExist:
#             return JsonResponse({"status": "fail", "error": "camera does not exist", 'data': request})
#         return JsonResponse({"snooze": camera_object.snooze}, status=status.HTTP_200_OK)
#
#     def post(self, request):
#         # schema = SnoozeCamera.schema
#         """
#         API endpoint to set snooze value - must contain snooze and camera_number in form-data
#         """
#
#         # Check if "snooze" key is present in the request data
#         if 'snooze' not in request.POST:
#             return JsonResponse({"status": "fail", "error": "requires snooze field"},
#                                 status=status.HTTP_400_BAD_REQUEST)
#         snooze: str = request.POST['snooze']
#         try:
#             new_value = strtobool(snooze)
#         except ValueError:
#             return JsonResponse({"status": "fail", "error": "invalid value for snooze"},
#                                 status=status.HTTP_400_BAD_REQUEST)
#         if 'camera_number' in request.POST:
#             camera_number = request.POST['camera_number']
#         else:
#             camera_number = None
#         try:
#             camera_object = Camera.objects.get(camera_number=camera_number)
#         except ObjectDoesNotExist:
#             return JsonResponse({"status": "fail", "error": "camera does not exist"}, status=status.HTTP_404_NOT_FOUND)
#         camera_object.snooze = new_value
#         camera_object.save()
#         return JsonResponse({"status": "success"}, status=status.HTTP_201_CREATED)
#     # def options(self, request, *args, **kwargs):
#     #     """
#     #     Don't include the view description in OPTIONS responses.
#     #     """
#     #     meta = self.metadata_class()
#     #     data = meta.determine_metadata(request, self)
#     #     data.pop('description')
#     #     return Response(data=data, status=status.HTTP_200_OK)
# def snooze_api(request):
#     permission_classes = [AllowAny]
#
#     if request.method == "POST":
#         if 'snooze' not in request.POST:
#             return JsonResponse({"status": "fail", "error": "requires snooze field"})
#         snooze: str = request.POST['snooze']
#         try:
#             new_value = strtobool(snooze)
#         except ValueError:
#             return JsonResponse({"status": "fail", "error": "invalid value for snooze"})
#         if 'camera_number' in request.POST:
#             camera_number = request.POST['camera_number']
#         else:
#             camera_number = None
#         try:
#             camera_object = Camera.objects.get(camera_number=camera_number)
#         except ObjectDoesNotExist:
#             return JsonResponse({"status": "fail", "error": "camera does not exist"})
#         camera_object.snooze = new_value
#         camera_object.save()
#         return JsonResponse({"status": "success"})
#     elif request.method == "GET":
#         if 'camera_number' in request.GET:
#             camera_number = request.GET['camera_number']
#         else:
#             return JsonResponse({"status": "fail", "error": "camera_number required for GET"})
#         try:
#             camera_object = Camera.objects.get(camera_number=camera_number)
#         except ObjectDoesNotExist:
#             return JsonResponse({"status": "fail", "error": "camera does not exist"})
#         return JsonResponse({"snooze": camera_object.snooze})
#     else:
#         return JsonResponse({"status": "fail", "error": "Only POST or GET methods allowed"})


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


def get_encrypted(password):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(password.encode())
    h_in_hex = h.hexdigest().upper()
    return h_in_hex


def get_license_details():
    f = Fernet(key)
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
    fingerprint_encrypted = get_encrypted(finger_print)
    mysql_password = fingerprint_encrypted[10:42][::-1]
    adm_details = check_adm_database(mysql_password)
    current_transaction_limit = adm_details['tx_limit']
    current_end_date = adm_details['end_date']
    current_camera_limit = adm_details['camera_limit']
    current_license_key = adm_details['license_key']
    # if not current_license_key:
    #     return None, None, None, None, None

    # check adm DB if license details exist - if so load them.  Need to modify compare_images_v4 and process_list
    # with new logic to get password license details.

    license_dict = {"end_date": current_end_date,
                    "purchased_transactions": current_transaction_limit,
                    "purchased_cameras": current_camera_limit,
                    "license_key": current_license_key,
                    "machine_uuid": _machine_uuid,
                    "root_fs_uuid": _root_fs_uuid,
                    "product_uuid": product_uuid}
    encoded_string = f.encrypt(str(license_dict).encode())
    return _machine_uuid, _root_fs_uuid, product_uuid, encoded_string, mysql_password


def license_limits_are_ok():
    # return True if all good - False if fails
    try:
        license_obj = Licensing.objects.last()
        if license_obj is None:  # Check if no object was found
            logger.error("Licensing Error - No License Found")
            return False

        # Proceed to check transaction count and date if object exists
        if (license_obj.transaction_count > license_obj.transaction_limit or
                datetime.date.today() > license_obj.end_date):
            logger.error(f"Licensing Error Current Transaction Count {license_obj.transaction_count} "
                         f"Transaction Limit {license_obj.transaction_limit} "
                         f"Expiry Date {license_obj.end_date}")
            return False
        else:
            return True
    except ObjectDoesNotExist:
        return False


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


def get_base_image(reference_images_list, url_id, regions, version):
    hour = int(timezone.localtime().strftime('%H'))

    hours = list(reference_images_list.values_list('hour', flat=True))

    hours = [int(item) for item in hours]
    hours.sort()

    closest_hour = str(take_closest(hours, hour)).zfill(2)
    try:

        closest_reference_image = ReferenceImage.objects.get(url_id=url_id, hour=closest_hour,
                                                             version=version).image
        base_image_file = f"{settings.MEDIA_ROOT}/{closest_reference_image}"
        img = cv2.imread(base_image_file)

        regions = ast.literal_eval(regions)
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
    # total_disk_giga_bytes = statvfs.f_frsize * statvfs.f_blocks / (1024 * 1024 * 1024)
    # total_disk_giga_bytes_free = round(statvfs.f_frsize * statvfs.f_bavail / (1024 * 1024 * 1024), 2)
    # total_disk_giga_bytes_used = round(total_disk_giga_bytes - total_disk_giga_bytes_free, 2)
    total_disk_bytes, total_disk_bytes_used, total_disk_bytes_free = shutil.disk_usage("/home/checkit")
    total_disk_giga_bytes = round(total_disk_bytes / (1024 ** 3), 2)
    total_disk_giga_bytes_free = round(total_disk_bytes_free / (1024 ** 3), 2)
    total_disk_giga_bytes_used = round(total_disk_bytes_used / (1024 ** 3), 2)
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
                    logger.info("Logfile {f} does not exist".format(f=log_file))
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
        # print(imported_data)
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
        actual_reference_image = obj.reference_image_id
        freeze_status = obj.freeze_status

        # time_stamp = datetime.datetime.now()
        # hour = time_stamp.strftime('%H')
        reference_images = ReferenceImage.objects.filter(url_id=camera_object.id)
        hours = []
        # TODO: dont think I need to worry about hours - each log record has its reference image in it.
        # for record in reference_images:
        #     hours.append(record.hour)
        # for i in range(0, len(hours)):
        #     hours[i] = int(hours[i])
        # hour = int(hour)
        # if hours:
            # absolute_difference_function = lambda list_value: abs(list_value - hour)
            # closest_hour = min(hours, key=absolute_difference_function)
            # closest_hour = str(closest_hour).zfill(2)
        try:
            reference_image = ReferenceImage.objects.get(pk=actual_reference_image)
            reference_image_date = reference_image.creation_date
        except ObjectDoesNotExist:
            context = {'result': "Capture Error", 'camera_name': camera_name,
                       'message': " - Unable to read Reference image"}
            return HttpResponse(template.render(context, request))
        image = reference_image.image
        base_image = cv2.imread(settings.MEDIA_ROOT + "/" + str(image))
        if base_image is None:
            context = {'result': "Capture Error", 'camera_name': camera_name,
                       'message': " - Unable to read Reference image"}
            return HttpResponse(template.render(context, request))
        else:
            local_time = timezone.localtime(reference_image_date).strftime("%Y-%m-%d %H:%M:%S")
            # base_image = cv2.putText(base_image, "Reference Image: " + local_time,
            #                          (50,50), fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=2,
            #                          color=(0,255,0), thickness=2, lineType=cv2.LINE_AA)

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
        capture_time_date = timezone.localtime(obj.creation_date).strftime("%Y-%m-%d %H:%M:%S")
        # merged_image = cv2.putText(merged_image, "Captured Image: " + local_time,
        #                              (50,50), fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=2,
        #                              color=(0,255,0), thickness=2, lineType=cv2.LINE_AA)
        merged_image_converted_to_binary = cv2.imencode('.png', merged_image)[1]
        base_64_merged_image = base64.b64encode(merged_image_converted_to_binary).decode('utf-8')
        context = {'capture_image': obj.image, 'reference_image': image, 'result': result,
                   'camera_name': camera_name, 'camera_number': camera_number,
                   'merged_image': base_64_merged_image, 'freeze_status': freeze_status,
                   'reference_image_date': reference_image_date, 'capture_time_date': obj.creation_date}
        # else:
        #     context = {'result': result, 'camera_name': camera_name, 'camera_number': camera_number}
        return HttpResponse(template.render(context, request))
    else:
        return redirect('logs')


# @permission_required('main_menu.add_enginestate')
@group_required('Scheduler')
def scheduler(request):
    user_name = request.user.username
    app = celery.Celery('camera_checker', broker='redis://localhost:6379')
    inspect = app.control.inspect()
    stats = inspect.stats()
    total_concurrency = 0
    if not stats:
        template = loader.get_template("500.html")
        context = {"error_message": "Unable to communicate with the Scheduler, please check if it is running"}
        logger.error("Unable to communicate with the Scheduler, please check if it is running")
        return HttpResponse(template.render(context, request))
    logger.info("User {u} access to Scheduler".format(u=user_name))

    template = loader.get_template('main_menu/scheduler.html')
    context = {}

    if request.FILES:
        if not license_limits_are_ok():
            template = loader.get_template('main_menu/license_error.html')
            context = {"license_error": "True"}
            return HttpResponse(template.render(context, request))
        uploaded_file = request.FILES['camera_list'].read()
        uploaded_file = uploaded_file.replace(b'\r\n', b'\n')
        uploaded_file = uploaded_file.decode().split("\n")
        uploaded_file = [int(item) for item in uploaded_file if item.isdigit()]

        # filtering out any record that has snooze
        matching_records = Camera.objects.filter(camera_number__in=uploaded_file)

        # Extract the items that exist in the model
        matching_items = matching_records.values_list('camera_number', flat=True)

        # Iterate over your list and check if each item exists in the model
        good_numbers = []
        bad_numbers = []
        for item in uploaded_file:
            if item in matching_items:
                good_numbers.append(item)
            else:
                bad_numbers.append(item)

        if bad_numbers:
            context = {"error": f"Invalid camera numbers in file - {bad_numbers}"}
            return HttpResponse(template.render(context, request))
        if good_numbers:
            template = loader.get_template('main_menu/scheduler_job_id.html')
            camera_ids = []
            for number in good_numbers:
                camera_object = Camera.objects.get(camera_number=number)
                # added check for snooze - principle is if snooze selected then never check anywhere,
                # if not camera_object.snooze:
                camera_ids.append(camera_object.id)
            number_of_cameras_in_run = len(camera_ids)
            # x = int(number_of_cpus/2)
            # num_sublists = (len(camera_ids) + x - 1) // x
            # sublists = [camera_ids[i * x: (i + 1) * x] for i in range(num_sublists)]
            # sublists = [camera_ids[i * x:int(len(camera_ids) / 7) * (i + 1)] for i in range(0, (x+1))]
            sublists = group_cameras_by_psn_ip(camera_ids)
            cleaned_sublist = [x for x in sublists if x]
            # create STARTED record first then create FINISHED and pass that record id to celery to have the
            # workers update the timestamp and counts as the complete check
            engine_state_record = EngineState(state="STARTED", state_timestamp=timezone.now(), user=user_name,
                                              number_of_cameras_in_run=number_of_cameras_in_run)
            engine_state_record.save()
            engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=timezone.now(), user=user_name,
                                              number_of_cameras_in_run=number_of_cameras_in_run)
            engine_state_record.save()
            engine_state_id = engine_state_record.id

            process_cameras.delay(cleaned_sublist, engine_state_id, user_name, force_check=False)
            context = {"jobid": engine_state_id}
            return HttpResponse(template.render(context, request))

    if request.method == 'POST' and 'start_engine' in request.POST:
        template = loader.get_template('main_menu/scheduler_job_id.html')
        if not license_limits_are_ok():
            template = loader.get_template('main_menu/license_error.html')
            context = {"license_error": "True"}
            return HttpResponse(template.render(context, request))

        logger.info("User {u} started engine".format(u=user_name))
        camera_objects = Camera.objects.all()
        camera_ids = [item.id for item in camera_objects]
        number_of_cameras_in_run = len(camera_ids)
        # x = int(number_of_cpus/2)
        # num_sublists = (len(camera_ids) + x - 1) // x
        # number_of_entries_in_list = len(camera_ids)// (number_of_cpus * 2)
        # sublists = [camera_ids[i * x: (i + 1) * x] for i in range(num_sublists)]
        # sublists = split_list(camera_ids, number_of_cpus * 2)
        sublists = group_cameras_by_psn_ip()
        cleaned_sublist = [x for x in sublists if x]
        # recommended configuration - set celery config file to have 2 x CPUs for concurrency and 2 workers
        # dual workers should provide some redundancy.
        # create STARTED record first then create FINISHED/ RUN COMPLETED and pass that record id to celery to have the
        # workers update the timestamp and counts as the complete check
        engine_state_record = EngineState(state="STARTED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_id = engine_state_record.id
        # process_cameras(camera_ids, engine_state_id, user_name)

        # for group_of_cameras in sublists:
            # process_cameras.delay(group_of_cameras, engine_state_id, user_name
        logger.info(f"STARTING ENGINE for Run Number {engine_state_id}")
        process_cameras.delay(cleaned_sublist, engine_state_id, user_name, force_check=False)
        context = {"jobid": engine_state_id}
        return HttpResponse(template.render(context, request))

    if request.method == 'POST' and 'camera_check' in request.POST:
        if not license_limits_are_ok():
            template = loader.get_template('main_menu/license_error.html')
            context = {"license_error": "True"}
            return HttpResponse(template.render(context, request))
        template = loader.get_template('main_menu/scheduler_job_id.html')
        input_number = request.POST.get('camera_check')
        try:
            camera_object = Camera.objects.get(camera_number=input_number)
        except ObjectDoesNotExist:

            context = {'camera_does_not_exist': input_number}
            template = loader.get_template('main_menu/scheduler.html')
            return HttpResponse(template.render(context, request))
        if camera_object.snooze:
            context = {"error": "Selected camera is on snooze mode"}
            template = loader.get_template('main_menu/scheduler.html')
            return HttpResponse(template.render(context, request))
        camera_id = [camera_object.id]
        number_of_cameras_in_run = 1
        engine_state_record = EngineState(state="STARTED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=timezone.now(), user=user_name,
                                          number_of_cameras_in_run=number_of_cameras_in_run)
        engine_state_record.save()
        engine_state_id = engine_state_record.id
        camera_id = [camera_id]
        process_cameras.delay(camera_id, engine_state_id, user_name, force_check=False)
        # process_cameras(camera_id, engine_state_id, user_name)

        context = {"jobid": engine_state_id}
        return HttpResponse(template.render(context, request))
    return HttpResponse(template.render(context, request))


# @login_required
@group_required('Licensing')
def licensing(request):
    user_name = request.user.username
    u = User.objects.get(username=user_name)
    # logger.info(f"group is {request.user.groups} {u.groups} {user_name}")
    # logging.info("User {u} access to Licensing".format(u=user_name))
    template = loader.get_template('main_menu/license.html')
    # get the actual state from the engine here and pass it to context
    obj = Licensing.objects.last()
    start_date = ""
    current_end_date = ""
    current_transaction_limit = ""
    current_transaction_count = ""
    current_camera_limit = ""
    license_owner = ""
    site_name = ""

    if obj:
        start_date = obj.start_date
        start_date = datetime.datetime.strftime(start_date, "%d-%B-%Y")
        current_end_date = obj.end_date
        current_end_date = datetime.datetime.strftime(current_end_date, "%d-%B-%Y")
        current_transaction_limit = obj.transaction_limit
        current_transaction_count = obj.transaction_count
        current_camera_limit = obj.camera_limit
        license_owner = obj.license_owner
        site_name = obj.site_name
    context = {'start_date': start_date, 'end_date': current_end_date, 'site_name': site_name,
               'transaction_limit': current_transaction_limit, 'license_owner': license_owner,
               'transaction_count': current_transaction_count, "camera_limit": current_camera_limit}

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
        try:
            license_details = ast.literal_eval(decrypted_file)
        except (SyntaxError, TypeError, ValueError, RecursionError) as e:
            context['status'] = f"ERROR: Invalid file {e}"
            return HttpResponse(template.render(context, request))
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
                        sql_statement = f"ALTER USER 'root'@'%' IDENTIFIED BY '{mysql_password}';"
                        # TODO setup root@"%" and checkit@"%"
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
                    logger.info(f"Failed all attempts at accessing database {e}")

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
                        logger.info(f"keys dont match  {new_license_key}, {uploaded_license_key}")
                        context['status'] = "ERROR: License keys mismatch"
                        return HttpResponse(template.render(context, request))
                else:
                    pass
                start_date = datetime.datetime.strftime(timezone.now(), "%Y-%m-%d")
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
                                           camera_limit=uploaded_purchased_cameras)
                try:
                    license_record.save()
                except Exception as e:
                    logger.info(f"licensing error {e}")
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
    # table_data = LogImage.objects.all()
    # paginator_class = LazyPaginator
    template_name = 'main_menu/log_table.html'
    paginate_by = 18
    filterset_class = LogFilter
    ordering = '-id'


    def get_queryset(self):
        # Get the base queryset
        qs = super().get_queryset()
        # Apply the filter to the queryset
        self.filterset = self.filterset_class(self.request.GET, queryset=qs)
        return self.filterset.qs  # Return the filtered queryset

# def get_date(request):
#     # if this is a POST request we need to process the form data
#     if request.method == 'POST':
#         # create a form instance and populate it with data from the request:
#         form = DateForm(request.POST)
#         # check whether it's valid:
#         if form.is_valid():
#             # process the data in form.cleaned_data as required
#             # ...
#             # redirect to a new URL:
#
#             return HttpResponse("value", form.cleaned_data)
#
#     # if a GET (or any other method) we'll create a blank form
#     else:
#         form = RegionsForm()
#
#     return render(request, 'main_menu/date.html', {'form': form})


class EngineStateView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = EngineState
    table_class = EngineStateTable
    template_name = 'main_menu/engine_state_table.html'
    paginate_by = 24
    filterset_class = EngineStateFilter
    ordering = 'state_timestamp'

    # def get_queryset(self):
    #     # You can manipulate the QuerySet here to exclude records based on a condition
    #     queryset = super().get_queryset()  # Get the original QuerySet
    #     return queryset.exclude(state='STARTED')

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


def write_pdf_pages(image_list, page_width, page_height, canvas_page, pass_or_fail):
    while len(image_list) > 0:
        left_margin_pos = 20
        top_margin_text_pos = 23
        top_margin_image_pos = 67
        second_image_pos = 85
        count = 0
        canvas_page.setFillColor(HexColor("#a2a391"))
        canvas_page.setStrokeColor(HexColor("#a2a391"))

        canvas_page.rect(0, 0, page_width, page_height, stroke=1, fill=1)
        # this creates a rectangle the size of the sheet
        canvas_page.setFillColor(HexColor("#000000"))
        canvas_page.setStrokeColor(HexColor("#000000"))

        canvas_page.setFont("Helvetica-BoldOblique", 18, )
        if pass_or_fail == "Triggered":
            canvas_page.drawString(*coord(110, 10, page_height, mm), text="Triggered Images Report")
        else:
            canvas_page.drawString(*coord(110, 10, page_height, mm), text="Pass Images Report")

        canvas_page.setFont("Helvetica", 10)
        canvas_page.drawString(*coord(270, 10, page_height, mm), text="Page " + str(canvas_page.getPageNumber()))
        for i in image_list[:3]:
            camera_name, camera_number, creation_time, base_image, matching_score, focus_value, log_image, light_level, current_focus_value, current_light_level, current_matching_threshold, user_name, run_number = i

            canvas_page.drawString(
                *coord(left_margin_pos, top_margin_text_pos + (count * top_margin_image_pos) - 5,
                       page_height, mm), text="Camera Name: " + camera_name)
            canvas_page.drawString(
                *coord(left_margin_pos + 87, top_margin_text_pos + (count * top_margin_image_pos) - 5,
                       page_height, mm), text="Camera Number: " + str(camera_number))
            canvas_page.drawString(
                *coord(left_margin_pos + 137, top_margin_text_pos + (count * top_margin_image_pos) - 5,
                       page_height, mm), text="Run Number: " + str(run_number))
            canvas_page.drawString(
                *coord(left_margin_pos + 177, top_margin_text_pos + (count * top_margin_image_pos) - 5,
                       page_height, mm), text="User: " + str(user_name))
            local_timezone = timezone.get_current_timezone()
            local_datetime = creation_time.astimezone(local_timezone)
            canvas_page.drawString(*coord(left_margin_pos, top_margin_text_pos + (count * top_margin_image_pos),
                                page_height, mm),
                         text="Capture: " + local_datetime.strftime("%d-%b-%Y %H:%M %p"))
            if matching_score < current_matching_threshold:
                canvas_page.setFillColor(HexColor("#CC0000"))
                canvas_page.setStrokeColor(HexColor("#000000"))
            else:
                canvas_page.setFillColor(HexColor("#000000"))
                canvas_page.setStrokeColor(HexColor("#000000"))
            canvas_page.drawString(*coord(left_margin_pos + 87, top_margin_text_pos + (count * top_margin_image_pos),
                                page_height, mm),
                                text="Matching Score: " + str(matching_score) + "/" + str(current_matching_threshold))
            if focus_value < current_focus_value:
                canvas_page.setFillColor(HexColor("#CC0000"))
                canvas_page.setStrokeColor(HexColor("#000000"))
            else:
                canvas_page.setFillColor(HexColor("#000000"))
                canvas_page.setStrokeColor(HexColor("#000000"))
            canvas_page.drawString(*coord(left_margin_pos + 129, top_margin_text_pos + (count * top_margin_image_pos),
                                page_height, mm), text="  Focus Value: " + str(focus_value)
                                                       + "/" + str(current_focus_value))
            if light_level < current_light_level:
                canvas_page.setFillColor(HexColor("#CC0000"))
                canvas_page.setStrokeColor(HexColor("#000000"))
            else:
                canvas_page.setFillColor(HexColor("#000000"))
                canvas_page.setStrokeColor(HexColor("#000000"))
            canvas_page.drawString(*coord(left_margin_pos + 177, top_margin_text_pos + (count * top_margin_image_pos),
                                page_height, mm), text="Light Level: " + str(light_level) +
                                                       "/" + str(current_light_level))
            canvas_page.setFillColor(HexColor("#000000"))
            canvas_page.setStrokeColor(HexColor("#000000"))

            image_rl = canvas.ImageReader(base_image)
            image_width, image_height = image_rl.getSize()
            scaling_factor = (image_width / page_width) * 1.3
            if 720 < image_width < 1920:
                scaling_factor = (1920/image_width) * scaling_factor

            if image_height > 1920:
                sf_multiplier = 2.311 / (image_width / image_height)
                scaling_factor = (image_width / page_width) * sf_multiplier
            canvas_page.setLineWidth(2)
            canvas_page.setStrokeColor(HexColor("#b9b6a9"))
            canvas_page.roundRect(left_margin_pos + 11,
                        page_height - (top_margin_image_pos + (count * top_margin_image_pos * mm)) - 139,
                        width=773, height=168, radius=4, stroke=1, fill=0)
            canvas_page.setStrokeColor(HexColor("#767368"))
            canvas_page.roundRect(left_margin_pos + 10,
                        page_height - (top_margin_image_pos + (count * top_margin_image_pos * mm)) - 140,
                        width=775, height=170, radius=4, stroke=1, fill=0)
            canvas_page.drawImage(image_rl,
                        *coord(left_margin_pos - 2,
                               top_margin_image_pos + (count * top_margin_image_pos) + 3,
                               page_height, mm),
                        width=image_width / (mm * scaling_factor),
                        height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)
            image_rl2 = canvas.ImageReader(log_image)
            image_width, image_height = image_rl.getSize()

            canvas_page.drawImage(image_rl2,
                        *coord(left_margin_pos + 2 + second_image_pos,
                               top_margin_image_pos + (count * top_margin_image_pos) + 3,
                               page_height, mm), width=image_width / (mm * scaling_factor),
                        height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)
            log_image_cv2 = cv2.imread(log_image)
            log_image_edges = get_transparent_edge(log_image_cv2, (0, 0, 255))
            log_image_edges = log_image_edges[:, :, :3]
            reference_image_cv2 = cv2.imread(base_image)
            merged_image = cv2.addWeighted(reference_image_cv2, 1, log_image_edges, 1, 0)
            # TODO change this non file based.
            cv2.imwrite("/tmp/merged_image.jpg", merged_image)
            image_rl3 = canvas.ImageReader("/tmp/merged_image.jpg")

            canvas_page.drawImage(image_rl3,
                        *coord(left_margin_pos + 2 + (2 * second_image_pos) + 5,
                               top_margin_image_pos + (count * top_margin_image_pos) + 3,
                               page_height, mm), width=image_width / (mm * scaling_factor),
                        height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)

            count += 1
        canvas_page.showPage()
        del image_list[:3]
    return canvas_page


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
                # logs = LogImage.objects.filter(creation_date__range=(start, end))
                logs = LogImage.objects.filter(run_number=i)
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
                             "pass_fail", "matching_score", "focus_value", "light_level", "Freeze Status" ,"creation_date",
                             "current_matching_threshold", "current_focus_value", "current_light_level", "user", "run_number"])
            # print(logs)
            for log in logs:
                local_timezone = timezone.get_current_timezone()
                local_datetime = log.creation_date.astimezone(local_timezone)
                writer.writerow([log.url.camera_name, log.url.camera_number, log.url.camera_location,
                                 log.action, log.matching_score, log.focus_value, log.light_level, log.freeze_status,
                                 datetime.datetime.strftime(local_datetime, "%d-%b-%Y %H:%M:%S"),
                                 log.current_matching_threshold, log.current_focus_value, log.current_light_level, log.user, log.run_number])

            return response

        elif request.POST.get('action') == "Export Triggered PDF":
            image_list_for_failed = []
            log = []
            base_image = ""
            for log in logs:
                if log.action == "Triggered":
                    camera_name = log.url.camera_name
                    camera_number = log.url.camera_number
                    # hour = str(log.creation_date.hour).zfill(2)
                    log_image = settings.MEDIA_ROOT + "/" + str(log.image)
                    if not os.path.exists(log_image):
                        logger.error(f"missing logfile {log_image}")
                        continue
                    # camera = Camera.objects.filter(id=log.url_id)
                    # print(camera)
                    # base_image = settings.MEDIA_ROOT + "/base_images/" + str(camera[0].id) + "/" + hour + ".jpg"
                    # base_image = settings.MEDIA_ROOT + "/" + str(log.reference_image)
                    base_image = settings.MEDIA_ROOT + "/" + str(log.reference_image.image)
                    if not os.path.exists(base_image):
                        logger.error(f"missing baseimage for logs {base_image}")
                        continue
                    matching_score = log.matching_score
                    current_matching_threshold = log.current_matching_threshold
                    focus_value = log.focus_value
                    light_level = log.light_level
                    current_focus_value = log.current_focus_value
                    current_light_level = log.current_light_level
                    user_name = log.user
                    run_number = log.run_number

                    image_list_for_failed.append((camera_name, camera_number, log.creation_date, base_image,
                                                  matching_score, focus_value, log_image, light_level,
                                                  current_focus_value, current_light_level,
                                                  current_matching_threshold, user_name, run_number))

            buffer_for_failed = io.BytesIO()
            canvas_for_failed = canvas.Canvas(buffer_for_failed, pagesize=landscape(A4))

            page_width, page_height = landscape(A4)
            if image_list_for_failed:
                canvas_for_failed = write_pdf_pages(image_list_for_failed, page_width,
                                                    page_height, canvas_for_failed, "Triggered")
                canvas_for_failed.save()
                buffer_for_failed.seek(0)
                return FileResponse(buffer_for_failed, as_attachment=True, filename='triggered_results.pdf')
            else:
                canvas_for_failed.setFillColor(HexColor("#a2a391"))
                canvas_for_failed.setStrokeColor(HexColor("#a2a391"))
                path = canvas_for_failed.beginPath()
                path.moveTo(0 * cm, 0 * cm)
                path.lineTo(0 * cm, 30 * cm)
                path.lineTo(25 * cm, 30 * cm)
                path.lineTo(25 * cm, 0 * cm)
                # this creates a rectangle the size of the sheet
                canvas_for_failed.drawPath(path, True, True)
                canvas_for_failed.setFillColor(HexColor("#000000"))
                canvas_for_failed.setStrokeColor(HexColor("#000000"))
                canvas_for_failed.setFont("Helvetica-BoldOblique", 18, )
                canvas_for_failed.drawString(*coord(25, 10, page_height, mm),
                             text="There are no triggered images for the selected records")
                canvas_for_failed.showPage()
                canvas_for_failed.save()
                buffer_for_failed.seek(0)
                return FileResponse(buffer_for_failed, as_attachment=True, filename='triggered_results.pdf')
        elif request.POST.get('action') == "Export Pass PDF":
            buffer_for_pass = io.BytesIO()
            canvas_for_pass = canvas.Canvas(buffer_for_pass, pagesize=landscape(A4))
            page_width, page_height = landscape(A4)
            image_list_for_pass = []

            for log in logs:
                if log.action == "Pass":
                    camera_name = log.url.camera_name
                    camera_number = log.url.camera_number
                    # hour = str(log.creation_date.hour).zfill(2)
                    # log_image = settings.MEDIA_ROOT + "/" + str(log.image)
                    log_image = settings.MEDIA_ROOT + "/" + str(log.image)
                    if not os.path.exists(log_image):
                        logger.error(f"missing logfile {log_image}")
                        continue
                    # camera = Camera.objects.filter(id=log.url_id)
                    # print(camera)
                    # base_image = settings.MEDIA_ROOT + "/base_images/" + str(camera[0].id) + "/" + hour + ".jpg"
                    base_image = settings.MEDIA_ROOT + "/" + str(log.reference_image.image)
                    if not os.path.exists(base_image):
                        logger.error(f"missing baseimage for logs {base_image}")
                        continue
                    matching_score = log.matching_score
                    current_matching_threshold = log.current_matching_threshold
                    focus_value = log.focus_value
                    light_level = log.light_level
                    current_focus_value = log.current_focus_value
                    current_light_level = log.current_light_level
                    user_name = log.user
                    run_number = log.run_number

                    image_list_for_pass.append((camera_name, camera_number, log.creation_date, base_image,
                                                matching_score, focus_value, log_image, light_level,
                                                current_focus_value, current_light_level,
                                                current_matching_threshold, user_name, run_number))
            if image_list_for_pass:
                canvas_for_pass = write_pdf_pages(image_list_for_pass, page_width,
                                                  page_height, canvas_for_pass, "Pass")
                canvas_for_pass.save()
                buffer_for_pass.seek(0)
                return FileResponse(buffer_for_pass, as_attachment=True, filename='pass_results.pdf')
            else:
                canvas_for_pass.setFillColor(HexColor("#a2a391"))
                canvas_for_pass.setStrokeColor(HexColor("#a2a391"))
                path = canvas_for_pass.beginPath()
                path.moveTo(0 * cm, 0 * cm)
                path.lineTo(0 * cm, 30 * cm)
                path.lineTo(25 * cm, 30 * cm)
                path.lineTo(25 * cm, 0 * cm)
                # this creates a rectangle the size of the sheet
                canvas_for_pass.drawPath(path, True, True)
                canvas_for_pass.setFillColor(HexColor("#000000"))
                canvas_for_pass.setStrokeColor(HexColor("#000000"))
                canvas_for_pass.setFont("Helvetica-BoldOblique", 18, )
                canvas_for_pass.drawString(*coord(25, 10, page_height, mm),
                             text="There are no pass images for the selected records")
                canvas_for_pass.showPage()
                canvas_for_pass.save()
                buffer_for_pass.seek(0)
                return FileResponse(buffer_for_pass, as_attachment=True, filename='pass_results.pdf')

    else:
        return HttpResponseRedirect("/state/")

# class SuggestedRegions:
#     def __init__(self, request):
#         self.request = request
#
#     def get_camera_ids(self):
#         # Get list of camera IDs from request
#         camera_ids = self.request.POST.getlist('camera_id')
#         return camera_ids
#
#     def is_commit_enabled(self):
#         # Check if commit flag is enabled in request
#         commit_flag = self.request.POST.get('commit', 'false').lower() == 'true'
#         return commit_flag
#
#     def is_status_enabled(self):
#         # Check if status flag is enabled in request
#         status_flag = self.request.POST.get('status', 'false').lower() == 'true'
#         return status_flag
#
#     def handle_request(self):
#         # Call appropriate method based on flags in request
#         camera_ids = self.get_camera_ids()
#         commit_enabled = self.is_commit_enabled()
#         status_enabled = self.is_status_enabled()
#
#         if commit_enabled:
#             self.commit(camera_ids)
#         if status_enabled:
#             self.status(camera_ids)
#         if camera_ids:
#             self.find_best_regions(camera_ids)
#
#     def find_best_regions(self, camera_ids):
#         # Find the best regions for given cameras
#         print(camera_ids)
#         pass
#
#     def commit(self, camera_ids):
#         # Commit changes to database for given cameras
#         print("commit", camera_ids)
#         pass
#
#     def status(self, camera_ids):
#         # Get current status of given cameras
#         print("status", camera_ids)
#         pass

# class TestAPI(APIView):
#     permission_classes = [IsAuthenticated]
#
#     @swagger_auto_schema(
#         operation_id="TestAPI",
#         description="Test API",
#         tags=["test"],
#
#     )
#     def post(self, request):
#         test_manager = SuggestedRegions(request)
#         tasks = test_manager.handle_request()
#         return Response({'tasks': tasks})


def split_into_groups(lst, y):
    avg = len(lst) / float(y)
    groups = []
    last = 0.0

    while last < len(lst):
        groups.append(lst[int(last):int(last + avg)])
        last += avg

    return groups


# @permission_required('main_menu.change_referenceimage')
@group_required('Regions')
def input_camera_for_regions(request):
    user_name = request.user.username
    logger.info("User {u} access to Regions".format(u=user_name))
    if request.method == 'POST' and 'input_list_for_find_best_regions' and request.FILES:


        uploaded_file = request.FILES['camera_list'].read()
        uploaded_file = uploaded_file.replace(b'\r\n', b'\n')
        uploaded_file = uploaded_file.decode().split("\n")
        uploaded_file = [int(item) for item in uploaded_file if item.isdigit()]

        # filtering out any record that has snooze
        matching_records = Camera.objects.filter(camera_number__in=uploaded_file)

        # Extract the items that exist in the model
        matching_items = matching_records.values_list('camera_number', flat=True)

        # Iterate over your list and check if each item exists in the model
        good_numbers = []
        bad_numbers = []
        for item in uploaded_file:
            if item in matching_items:
                good_numbers.append(item)
            else:
                bad_numbers.append(item)

        if bad_numbers:
            message =  f"Invalid camera numbers in file - {bad_numbers}"
            superuser = True
            return render(request, 'main_menu/regions.html',
                          {'message': message, 'superuser': superuser})

        if good_numbers:
            camera_ids = []
            for number in good_numbers:
                camera_object = Camera.objects.get(camera_number=number)
                # added check for snooze - principle is if snooze selected then never check anywhere,
                # if not camera_object.snooze:
                camera_ids.append(camera_object.id)

            x = int(number_of_cpus)
            sublists = split_into_groups(camera_ids, x)
            cleaned_sublist = [x for x in sublists if x]
            for cameras in cleaned_sublist:
                find_best_regions.delay(cameras)

            message = ""
            superuser = True
            return render(request, 'main_menu/regions.html',
                          {'message': message, 'superuser': superuser})

    if request.method == 'POST' and 'find_best_regions' in request.POST:
        # print("Got best regions")

        camera_objects = Camera.objects.all()
        camera_ids = [item.id for item in camera_objects]
        number_of_cameras_in_run = len(camera_ids)
        x = int(number_of_cpus)
        # num_sublists = (len(camera_ids) + x - 1) // x
        # sublists = [camera_ids[i * x: (i + 1) * x] for i in range(x)]
        sublists = split_into_groups(camera_ids, x)
        cleaned_sublist = [x for x in sublists if x]
        for cameras in cleaned_sublist:
            find_best_regions.delay(cameras)
        # start_find_best_regions.delay(sublists)

        #start_find_best_regions
        # task_signatures = [find_best_regions.s(numbers) for numbers in sublists]
        # job = group(task_signatures)
        # result = job.apply_async()
        # try:
        #     result.save()
        # except AttributeError:
        #     pass
        # result = find_best_regions.delay(camera_ids)
        # for group_of_cameras in sublists:
        #     find_best_regions.delay(group_of_cameras)

        # while not result.ready():
        #     time.sleep(1)
        # message = result.get()
        # message = result.id
        # # print(message, result.backend)
        # request.session['task_id'] = result.id
        # request.session.save()  # Save session data
        # # print('message', message)
        message = ""
        superuser = True
        return render(request, 'main_menu/regions.html',
                      {'message': message, 'superuser': superuser})

    if request.method == 'POST' and 'status' in request.POST:
        task_id = request.session.get('task_id')

        # if task_id:
            # Retrieve AsyncResult object using task ID
            # result = AsyncResult(task_id)
            # try:
            #     result = GroupResult.restore(task_id)
            # except AttributeError:
            #     message = "No Result"
            #     return render(request, 'main_menu/regions.html', {'message': message})
            #
            # if not result:
            #     message = "Not Ready"
            #     return render(request, 'main_menu/regions.html', {'message': message})

            # if result.ready():
            #     print(result.get())  # Return task result if ready
            #     # try:
            #     #     SuggestedValues.objects.all().delete()
            #     # except:
            #     #     pass
            #     # for data in result.get():
            #     #     instances = [SuggestedValues(camera_id=str(item[0]), regions=item[1]) for item in data]
            #     #
            #     #     SuggestedValues.objects.bulk_create(instances)
        table = SuggestedValuesTable(SuggestedValues.objects.all())
        table.paginate(page=request.GET.get("page", 1), per_page=5)
        return render(request, "main_menu/best_regions_table.html", {
            "table": table})
                # message = ""
                # return render(request, 'main_menu/regions.html', {'message': message})
        #     else:
        #         message = ""
        #         superuser = True
        #         return render(request, 'main_menu/regions.html',
        #                       {'message': message, 'superuser': superuser})
        # else:
        #     message = ""
        #     superuser = True
        #     return render(request, 'main_menu/regions.html',
        #                   {'message': message, 'superuser': superuser })
    if request.method == 'POST' and 'reset_auto_regions' in request.POST:
        SuggestedValues.objects.all().delete()
        message = ""
        superuser = True
        return render(request, 'main_menu/regions.html',
                      {'message': message, 'superuser': superuser})

    if request.method == 'POST' and 'commit' in request.POST:
        suggested_values = SuggestedValues.objects.all()
        for suggested_value in suggested_values:
            camera_object = Camera.objects.get(id=suggested_value.url_id)
            camera_object.matching_threshold = suggested_value.new_matching_score
            camera_object.focus_value_threshold = suggested_value.new_focus_value
            camera_object.light_level_threshold = suggested_value.new_light_level
            camera_object.image_regions = suggested_value.new_regions
            camera_object.save()
        SuggestedValues.objects.all().delete()
        selected_ids = request.POST.getlist('selection')
        # print(selected_ids)
        message = ""
        superuser = True
        return render(request, 'main_menu/regions.html',
                      {'message': message, 'superuser': superuser})

    # if request.method == 'POST' and 'copy_references' in request.POST:
    #     reverse("copy_references")


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
        reference_images = ReferenceImage.objects.filter(url_id=url_id, version=camera_object.reference_image_version)
        if reference_images:
            base64_image = get_base_image(reference_images, url_id, regions, camera_object.reference_image_version)
            try:
                log_obj = LogImage.objects.filter(url_id=url_id, action__in=["Pass", "Triggered"]).last()
                if not log_obj:
                    raise ObjectDoesNotExist
                else:
                    region_scores = log_obj.region_scores
                    if isinstance(region_scores, str):
                        region_scores = json.loads(region_scores)
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

        if request.user.is_superuser:
            superuser = True
        else:
            superuser = False
        page = request.GET.get('page')
        if page:
            table = SuggestedValuesTable(SuggestedValues.objects.all())
            table.paginate(page=request.GET.get("page", page), per_page=5)
            return render(request, "main_menu/best_regions_table.html", {
                "table": table})
        else:
            return render(request, 'main_menu/regions.html',
                          {'message': message, 'superuser': superuser})


# @permission_required('main_menu.change_referenceimage')
@group_required('Regions')
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
        reference_images = ReferenceImage.objects.filter(url_id=camera_object.id,
                                                         version=camera_object.reference_image_version)
        if reference_images:
            base64_image = get_base_image(reference_images, url_id, regions, camera_object.reference_image_version)
            try:
                log_obj = LogImage.objects.filter(url_id=url_id, action__in=["Pass", "Triggered"]).last()
                if not log_obj:
                    raise ObjectDoesNotExist
                else:
                    region_scores = log_obj.region_scores
                    if isinstance(region_scores, str):
                        region_scores = json.loads(region_scores)
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


def get_engine_status(request):
    app = celery.Celery('camera_checker', broker='redis://localhost:6379')
    app_status = app.control.inspect().active()
    running = False
    if app_status:
        for value in app_status.values():
            if value != []:
                running = True
    data = {'progress': running}
    response = JsonResponse(data)
    return response


def progress_meter(request):
    return render(request, "main_menu/progress_meter.html")


def cameras_with_missing_reference_images(request):
    table = CameraTable(Camera.objects.exclude(referenceimage__isnull=False))

    return render(request, "main_menu/camera_table.html", {
        "table": table
    })


def action_per_hour_report(request):
    # Get the current time
    current_time = timezone.now()

    # Calculate the start time (e.g., last 24 hours)
    start_time = current_time - datetime.timedelta(days=3)

    # Query the database to count the number of cameras for each action per hour
    results = (
        LogImage.objects
        .filter(creation_date__range=(start_time, current_time))
        .annotate(hour=TruncHour('creation_date'))
        .values('hour', 'action')
        .annotate(count=Count('url'))
        .order_by('hour', 'action')
    )
    table = LogSummaryTable(results)
    return render(request, 'main_menu/log_summary.html', {'table': table})


@shared_task(name='main_menu.views.check_all_cameras', time_limit=28800, soft_time_limit=28800)
def check_all_cameras():
    user_name = "system_scheduler"
    camera_objects = Camera.objects.all()
    camera_ids = [item.id for item in camera_objects]
    # x = int(number_of_cpus/2)
    # num_sublists = (len(camera_ids) + x - 1) // x
    # sublists = [camera_ids[i * x: (i + 1) * x] for i in range(num_sublists)]
    number_of_cameras_in_run = len(camera_ids)
    sublists = group_cameras_by_psn_ip()
    # [ [12725, 1276], [1345, 1357, 1367] ]
    cleaned_sublists = [x for x in sublists if x]
    # flattened_list = []
    # for sublist in cleaned_sublists:
    #     flattened_list.extend(sublist)

    # create STARTED record first then create FINISHED and pass that record id to celery to have the
    # workers update the timestamp and counts as the complete check
    engine_state_record = EngineState(state="STARTED", state_timestamp=timezone.now(), user=user_name,
                                      number_of_cameras_in_run=number_of_cameras_in_run)
    engine_state_record.save()
    engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=timezone.now(), user=user_name,
                                      number_of_cameras_in_run=number_of_cameras_in_run)
    engine_state_record.save()
    engine_state_id = engine_state_record.id
    logger.info(f"SCHEDULER STARTED for Run Number {engine_state_id}")
    # for group_of_cameras in sublists:
    #     process_cameras.delay(group_of_cameras, engine_state_id, user_name)
    logger.info(f"FORM VIEWS camera list {cleaned_sublists}")
    process_cameras.delay(cleaned_sublists, engine_state_id, user_name, force_check=False)



# @shared_task
# def check_groups(groups, *args, **kwargs):
#     # Your task logic here
#     logger.info(f"Checking group: {groups}")
#     camera_ids = []
#     for grp in groups:
#         logger.info(f"Processing Group {grp}")
#         cameras = Camera.objects.filter(group_name=grp)
#         for camera in cameras:
#             camera_ids.append(camera.id)
#             logger.info(f"Camera number{camera.camera_number} Camera Name {camera.camera_name} ")
#     logger.info(f"Cameras to check {camera_ids}")
#     user_name = "system_scheduler"
#     # camera_objects = Camera.objects.all()
#     # camera_ids = [item.id for item in camera_objects]
#     # # x = int(number_of_cpus/2)
#     # # num_sublists = (len(camera_ids) + x - 1) // x
#     # # sublists = [camera_ids[i * x: (i + 1) * x] for i in range(num_sublists)]
#     number_of_cameras_in_run = len(camera_ids)
#     sublists = group_cameras_by_psn_ip()
#
#     # create STARTED record first then create FINISHED and pass that record id to celery to have the
#     # workers update the timestamp and counts as the complete check
#     engine_state_record = EngineState(state="STARTED", state_timestamp=timezone.now(), user=user_name,
#                                       number_of_cameras_in_run=number_of_cameras_in_run)
#     engine_state_record.save()
#     engine_state_record = EngineState(state="RUN COMPLETED", state_timestamp=timezone.now(), user=user_name,
#                                       number_of_cameras_in_run=number_of_cameras_in_run)
#     engine_state_record.save()
#     engine_state_id = engine_state_record.id
#     # for group_of_cameras in sublists:
#     #     process_cameras.delay(group_of_cameras, engine_state_id, user_name)
#     process_cameras.delay(sublists, engine_state_id, user_name)

def copy_reference_images(request):
    filter_form = FilterForm(request.GET or None)

    # --- Build version choices BEFORE instantiating/validating the form ---
    versions_list = []
    version_choices = None  # we'll pass into the form

    camera_number_raw = request.GET.get('camera_number')  # raw string is fine
    if camera_number_raw:
        try:
            cam_num = int(camera_number_raw)
            camera = Camera.objects.get(camera_number=cam_num)
            url_id = camera.id
            versions_list = (ReferenceImage.objects
                             .filter(url_id=url_id)
                             .values_list('version', flat=True)
                             .distinct()
                             .order_by('version'))
            if versions_list:
                version_choices = [('', '— pick a version —')] + [(str(v), str(v)) for v in versions_list]
            else:
                version_choices = [('', 'No versions for this camera')]
        except (ValueError, Camera.DoesNotExist):
            version_choices = [('', 'No versions for this camera')]

    # Now instantiating the form with the choices pre-populated
    filter_form = FilterForm(request.GET or None, version_choices=version_choices)

    # Default queryset
    queryset = ReferenceImage.objects.all()

    if filter_form.is_valid():
        camera_number = filter_form.cleaned_data.get('camera_number')
        version_raw = filter_form.cleaned_data.get('version')  # string from ChoiceField

        if camera_number is not None:
            try:
                camera = Camera.objects.get(camera_number=camera_number)
                url_id = camera.id

                if version_raw:  # only filter by version if user picked one
                    queryset = ReferenceImage.objects.filter(url_id=url_id, version=int(version_raw))
                else:
                    queryset = ReferenceImage.objects.filter(url_id=url_id)
            except Camera.DoesNotExist:
                # fall back and show error
                table = ReferenceImageTable(queryset)
                table.paginate(page=request.GET.get("page", 1), per_page=24)
                return render(request, "main_menu/select_regions_table.html", {
                    'filter_form': filter_form,
                    'error_message': "Camera number does not exist",
                    'table': table,
                })

    if request.method == 'POST':
        selection = request.POST.getlist("selection")
        selected_hours = request.POST.getlist('hour')
        # print("selection", selection)
        # print("selected_hours", selected_hours)
        if len(selection) != 1:
            # queryset = ReferenceImage.objects.all()
            #
            # table = ReferenceImageTable(queryset)
            # table.paginate(page=request.GET.get("page", 1), per_page=24)
            return render(request, "main_menu/select_regions_table.html", {'filter_form': filter_form,
                                                                           "error_message": "Please select one reference image you wish to copy", "table": table})
        if not selected_hours:
            # queryset = ReferenceImage.objects.all()
            #
            # table = ReferenceImageTable(queryset)
            # table.paginate(page=request.GET.get("page", 1), per_page=24)
            return render(request, "main_menu/select_regions_table.html",
                          {'filter_form': filter_form,
                           "error_message": "Please select the hours to copy the reference image to",
                           "table": table})

        # Do copy here
        source_reference_image_object = ReferenceImage.objects.get(id=selection[0])
        image = source_reference_image_object.image
        version = str(source_reference_image_object.version).zfill(4)
        url_id = source_reference_image_object.url_id
        for hour in selected_hours:
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
                    return render(request, "main_menu/select_regions_table.html",
                              {'filter_form': filter_form,
                               "error_message": f"Error copying reference image - {result.stderr}",
                               "table": table})
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
                        return render(request, "main_menu/select_regions_table.html",
                                      {'filter_form': filter_form,
                                       "error_message": f"Error copying reference image - {result.stderr}",
                                       "table": table})
                except Exception as e:
                    # table = ReferenceImageTable(queryset)
                    # table.paginate(page=request.GET.get("page", 1), per_page=24)
                    return render(request, "main_menu/select_regions_table.html",
                                  {'filter_form': filter_form,
                                   "error_message": f"Error creating new reference image - {e}",
                                   "table": table})
                # print("Creating new hour")
                all_new_reference_images = ReferenceImage.objects.filter(url_id=url_id, version=source_reference_image_object.version)
                
                if ReferenceImage.objects.filter(url_id=url_id, version=source_reference_image_object.version).count() == 24:
                    try:

                        Camera.objects.filter(pk=url_id).update(trigger_new_reference_image=False)
                        Camera.objects.filter(pk=url_id).update(reference_image_version=source_reference_image_object.version)
                        
                    except ObjectDoesNotExist:
                        logger.error(f"Unbale to update original camera unique id {url_id}")


        # queryset = ReferenceImage.objects.all()
        # table = ReferenceImageTable(queryset)
        # table.paginate(page=request.GET.get("page", 1), per_page=24)
        return render(request, "main_menu/select_regions_table.html",
                          {'filter_form': filter_form,
                           "error_message": "Successfully copied",
                           "table": table})

    table = ReferenceImageTable(queryset)
    table.paginate(page=request.GET.get("page", 1), per_page=24)
    return render(request, "main_menu/select_regions_table.html", {'filter_form': filter_form,
        "table": table})


def migrate_reference_images(request):
    buffer_for_download = io.BytesIO()
    if request.method == "POST" and request.FILES and "input_list_for_migration" in request.POST:

        uploaded_file = request.FILES['camera_list'].read()
        uploaded_file = uploaded_file.replace(b'\r\n', b'\n')
        uploaded_file = uploaded_file.decode().split("\n")
        uploaded_file = [int(item) for item in uploaded_file if item.isdigit()]

        # filtering out any record that has snooze
        matching_records = Camera.objects.filter(camera_number__in=uploaded_file)

        # Extract the items that exist in the model
        matching_items = matching_records.values_list('camera_number', flat=True)

        # Iterate over your list and check if each item exists in the model
        good_numbers = []
        bad_numbers = []
        for item in uploaded_file:
            if item in matching_items:
                good_numbers.append(item)
            else:
                bad_numbers.append(item)

        if bad_numbers:
            message = f"Invalid camera numbers in file - {bad_numbers}"
            superuser = True
            return render(request, 'main_menu/regions.html',
                          {'message': message, 'superuser': superuser})

        if good_numbers:
            camera_ids = []
            for number in good_numbers:
                camera_object = Camera.objects.get(camera_number=number)
                # added check for snooze - principle is if snooze selected then never check anywhere,
                # if not camera_object.snooze:
                camera_ids.append(camera_object.id)

            # x = int(number_of_cpus)
            # sublists = split_into_groups(camera_ids, x)
            # cleaned_sublist = [x for x in sublists if x]
            camera_csv_buffer = io.StringIO()
            camera_writer = csv.writer(camera_csv_buffer)
            fieldnames = [
                'url',
                'multicast_address',
                'multicast_port',
                'camera_username',
                'camera_password',
                'camera_number',
                'camera_name',
                'camera_location',
                'image_regions',
                'matching_threshold',
                'focus_value_threshold',
                'light_level_threshold',
                'creation_date',
                'last_check_date',
                'snooze',
                'trigger_new_reference_image',
                'freeze_check',
                'trigger_new_reference_image_date',
                'reference_image_version',
                'group_name_id'
            ]
            camera_writer.writerow(fieldnames)
            for camera_number in good_numbers:
                camera = Camera.objects.get(camera_number=camera_number)
                camera.image_regions = camera.image_regions.replace("'","")
                camera_dict = {
                    'url': camera.url,
                    'multicast_address': str(camera.multicast_address),
                    'multicast_port': camera.multicast_port,
                    'camera_username': camera.camera_username,
                    'camera_password': camera.camera_password,
                    'camera_number': camera.camera_number,
                    'camera_name': camera.camera_name,
                    'camera_location': camera.camera_location,
                    'image_regions': camera.image_regions,
                    'matching_threshold': camera.matching_threshold,
                    'focus_value_threshold': camera.focus_value_threshold,
                    'light_level_threshold': camera.light_level_threshold,
                    'creation_date': camera.creation_date.strftime('%Y-%m-%d %H:%M:%STZ %Z%z'),
                    'last_check_date': camera.last_check_date.strftime('%Y-%m-%d %H:%M:%STZ %Z%z'),
                    'snooze': camera.snooze,
                    'trigger_new_reference_image': camera.trigger_new_reference_image,
                    'freeze_check': camera.freeze_check,
                    'trigger_new_reference_image_date': camera.trigger_new_reference_image_date.strftime(
                        '%Y-%m-%d %H:%M:%STZ %Z%z'),
                    'reference_image_version': camera.reference_image_version,
                    'group_name_id': camera.group_name_id
                }

                # Write the row to the CSV file
                camera_writer.writerow([camera_dict[field] for field in fieldnames])
            camera_csv_bytes = camera_csv_buffer.getvalue().encode('utf-8')
            camera_csv_file = io.BytesIO(camera_csv_bytes)
            camera_csv_file.seek(0)

            fieldnames = [
                'old_id',
                'camera_number',
                'image',
                'hour',
                'light_level',
                'focus_value',
                'creation_date',
                'version'
            ]
            reference_csv_buffer = io.StringIO()
            reference_writer = csv.writer(reference_csv_buffer)
            reference_writer.writerow(fieldnames)

            for camera_number in good_numbers:
                camera_object = Camera.objects.get(camera_number=camera_number)
                reference_objects = ReferenceImage.objects.filter(url=camera_object.id)
                for reference_object in reference_objects:
                    reference_dict = {
                        'old_id': camera_object.id,
                        'camera_number': camera_object.camera_number,
                        'image': reference_object.image,
                        'hour': reference_object.hour,
                        'light_level': reference_object.light_level,
                        'focus_value': reference_object.focus_value,
                        'creation_date': reference_object.creation_date.strftime('%Y-%m-%d %H:%M:%STZ %Z%z'),
                        'version': reference_object.version
                    }
                    reference_writer.writerow([reference_dict[field] for field in fieldnames] )
            reference_csv_bytes = reference_csv_buffer.getvalue().encode('utf-8')
            reference_csv_file = io.BytesIO(reference_csv_bytes)
            reference_csv_file.seek(0)

            with tarfile.open(fileobj=buffer_for_download, mode='w:gz') as tar:
                info = tarfile.TarInfo(name=f'camera_export-{datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")}.csv')
                info.size = len(camera_csv_bytes)
                tar.addfile(tarinfo=info, fileobj=camera_csv_file)
                info = tarfile.TarInfo(
                    name=f'reference_export-{datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")}.csv')
                info.size = len(reference_csv_bytes)
                tar.addfile(tarinfo=info, fileobj=reference_csv_file)

                for camera_number in good_numbers:
                    camera = Camera.objects.get(camera_number=camera_number)
                    reference_images = ReferenceImage.objects.filter(url=camera.id, version=camera.reference_image_version)
                    for reference_image in reference_images:
                        reference_image_file = reference_image.image.name
                        tar.add(settings.MEDIA_ROOT + "/" + reference_image_file, arcname=reference_image_file)

            buffer_for_download.seek(0)

            # return FileResponse(tarfile, as_attachment=True, filename='tar_file.tar')
            response = StreamingHttpResponse(buffer_for_download, content_type='application/gzip')
            response['Content-Disposition'] = 'attachment; filename="migration_archive.tar.gz"'
            return response
    if request.method == "POST" and request.FILES and "input_archive_migration" in request.POST:
        pass
        tar_file = request.FILES['tar_file']
        logger.info(len(tar_file))
        with tarfile.open(fileobj=tar_file, mode='r') as tar:
            camera_csv_file_name = next((f for f in tar.getmembers() if f.name.startswith("camera_export")), None)
            reference_csv_file_name = next((f for f in tar.getmembers() if f.name.startswith("reference_export")), None)
            image_files_names = [f for f in tar.getmembers() if f.name.startswith("base_images")]
            camera_csv_extract = tar.extractfile(camera_csv_file_name)
            if camera_csv_extract:
                camera_csv_bytes = BytesIO(camera_csv_extract.read())
                csv_lines = camera_csv_bytes.getvalue().decode('utf-8').splitlines()
                headers = csv_lines[0].strip().split(',')
                headers = [header.strip() for header in headers]
                for line in csv_lines[1:]:
                    # data = line.strip().split(',')
                    # data = [item.strip() for item in data]
                    reader = csv.reader([line])
                    data = list(reader)[0]
                    row_dict = {headers[i]: data[i] for i in range(len(headers))}
                    converted_row = {}
                    for key, value in row_dict.items():
                        field = Camera._meta.get_field(key)
                        # if isinstance(field, models.CharField) and field.name == "image_regions":
                        #     converted_row[key] = value.strip("\'")

                        if isinstance(field, (models.DateTimeField)):
                            try:
                                dt = value.replace("TZ", '')
                                date_val = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S %Z%z")
                                converted_row[key] = date_val
                            except ValueError:
                                print(f"Skipping {key} due to invalid date format")
                                continue  # or set to None as needed
                        elif isinstance(field, models.IntegerField):
                            if value.strip() == '':
                                converted_row[key] = None
                            else:
                                converted_row[key] = int(value)
                        elif isinstance(field, models.BooleanField):
                            if value.strip() == '':
                                converted_row[key] = None
                            else:
                                # converted_row[key] = bool(value)
                                converted_row[key] = value.lower() == 'true'
                        elif isinstance(field, models.DecimalField):
                            if value.strip() == '':
                                converted_row[key] = None
                            else:
                                converted_row[key] = float(value)
                        # Add more field types as needed
                        else:
                            if value == "None":
                                value = None
                            converted_row[key] = value
                    try:
                        if Camera.objects.filter(camera_number=row_dict['camera_number']).exists():
                            # Update existing record or create new if not exists
                            # if row_dict['multicast_address'] == 'None':
                            #     updates = {
                            #         'url': row_dict['url'],
                            #         'multicast_port': converted_row['multicast_port'],
                            #         'camera_username': converted_row['camera_username'],
                            #         'camera_password': converted_row['camera_password'],
                            #         'camera_number': converted_row['camera_number'],
                            #         'camera_name': converted_row['camera_name'],
                            #         'camera_location': converted_row['camera_location'],
                            #         'image_regions': converted_row['image_regions'],
                            #         'matching_threshold': converted_row['matching_threshold'],
                            #         'focus_value_threshold': converted_row['focus_value_threshold'],
                            #         'light_level_threshold': converted_row['light_level_threshold'],
                            #         'creation_date': converted_row['creation_date'],
                            #         'last_check_date': converted_row['last_check_date'],
                            #         'snooze': converted_row['snooze'],
                            #         'trigger_new_reference_image': converted_row['trigger_new_reference_image'],
                            #         'freeze_check': converted_row['freeze_check'],
                            #         'trigger_new_reference_image_date': converted_row['trigger_new_reference_image_date'],
                            #         'reference_image_version': converted_row['reference_image_version'],
                            #         'group_name_id': converted_row['group_name_id']
                            #     }
                            #     Camera.objects.filter(camera_number=row_dict['camera_number']).update(**updates)
                            #     logger.info(f"Updated {Camera.__name__} with camera number: {row_dict['camera_number']}")
                            # else:
                            #     Camera.objects.create(**converted_row)
                            #     logger.info(f"Created {Camera.__name__} with camera number: {row_dict['camera_number']}")
                            Camera.objects.filter(camera_number=row_dict['camera_number']).update(**converted_row)
                            Camera.objects.get(camera_number=row_dict['camera_number']).scheduled_hours.set(
                                HoursInDay.objects.all())
                            Camera.objects.get(camera_number=row_dict['camera_number']).scheduled_days.set(
                                DaysOfWeek.objects.all())
                            print(Camera.objects.get(camera_number=row_dict['camera_number']).scheduled_hours.all())
                            print(Camera.objects.get(camera_number=row_dict['camera_number']).scheduled_days.all())
                        else:
                            # create record
                            Camera.objects.create(**converted_row)
                            Camera.objects.get(camera_number=row_dict['camera_number']).scheduled_hours.set(
                                HoursInDay.objects.all())
                            Camera.objects.get(camera_number=row_dict['camera_number']).scheduled_days.set(
                                DaysOfWeek.objects.all())
                            logger.info(f"Created {Camera.__name__} with camera number: {row_dict['camera_number']}")

                    except Exception as e:
                        logger.error(f"Error processing line: {e}")

            reference_csv_extract = tar.extractfile(reference_csv_file_name)

            if reference_csv_extract:
                reference_csv_bytes = BytesIO(reference_csv_extract.read())
                csv_lines = reference_csv_bytes.getvalue().decode('utf-8').splitlines()
                headers = csv_lines[0].strip().split(',')
                headers = [header.strip() for header in headers]
                for line in csv_lines[1:]:
                    # data = line.strip().split(',')
                    # data = [item.strip() for item in data]
                    reader = csv.reader([line])
                    data = list(reader)[0]
                    row_dict = {headers[i]: data[i] for i in range(len(headers))}
                    converted_row = {}
                    camera_object = Camera.objects.get(camera_number=row_dict['camera_number'])
                    url = camera_object
                    new_id = camera_object.id
                    # url = Camera.objects.get(camera_number=row_dict['camera_number'])
                    del row_dict['camera_number']
                    old_id = row_dict['old_id']
                    del row_dict['old_id']
                    for key, value in row_dict.items():
                        field = ReferenceImage._meta.get_field(key)
                        # if isinstance(field, models.CharField) and field.name == "image_regions":
                        #     converted_row[key] = value.strip("\'")

                        if isinstance(field, (models.DateTimeField)):
                            try:
                                dt = value.replace("TZ", '')
                                date_val = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S %Z%z")
                                converted_row[key] = date_val
                            except ValueError:
                                logger.error(f"Skipping {key} due to invalid date format")
                                continue  # or set to None as needed
                        elif isinstance(field, models.IntegerField):
                            if value.strip() == '':
                                converted_row[key] = None
                            else:
                                converted_row[key] = int(value)
                        elif isinstance(field, models.BooleanField):
                            if value.strip() == '':
                                converted_row[key] = None
                            else:
                                converted_row[key] = bool(value)
                        elif isinstance(field, models.DecimalField):
                            if value.strip() == '':
                                converted_row[key] = None
                            else:
                                converted_row[key] = float(value)
                        # Add more field types as needed
                        else:
                            if value == "None":
                                value = None
                            converted_row[key] = value

                    try:

                        # Update existing record or create new if not exists
                        # if row_dict['multicast_address'] == 'None':
                            # updates = {
                            #     'camera_number': converted_row['camera_number'],
                            #     'image': converted_row['image'],
                            #     'hour': converted_row['hour'],
                            #     'image_regions': converted_row['image_regions'],
                            #     'light_level': converted_row['light_level'],
                            #     'focus_value': converted_row['focus_value'],
                            #     'creation_date': converted_row['creation_date'],
                            #     'version': converted_row['version'],
                            # }
                            # Update existing record or create new if not exists
                        converted_row['image'] = str(converted_row['image']).replace(str(old_id), str(url.id))
                        obj, created = ReferenceImage.objects.update_or_create(
                            url=url, hour=row_dict['hour'],
                            defaults=converted_row,
                        )
                        if created:
                            logger.info(f"Created {ReferenceImage.__name__} with camera: {url.camera_number}")
                        else:
                            logger.info(f"Updated {ReferenceImage.__name__} with camera: {url.camera_number}")
                        # else:
                        #     # Create new record
                        #     ReferenceImage.objects.create(**converted_row)
                        #     print(f"Created new {ReferenceImage.__name__}")

                        for file in image_files_names:
                            hour_ext = row_dict['hour'] + ".jpg"
                            if file.name.endswith(hour_ext) and file.name.startswith(f"base_images/{old_id}"):
                                logger.info(f"found file {file.name}")
                                file_object = tar.extractfile(file)
                                file_data = file_object.read()
                                os.makedirs(f"/home/checkit/camera_checker/media/base_images/{url.id}", exist_ok=True)
                                new_file_name  = file.name.replace(f"base_images/{old_id}/", "")
                                with open(f"/home/checkit/camera_checker/media/base_images/{url.id}/{new_file_name}", "wb") as f:
                                    f.write(file_data)
                                    f.close()
                    except Exception as e:
                        logger.info(f"Error processing line: {e}")

            print("file_names")

    if request.method == 'POST' and request.FILES and "synergy_import_file" in request.POST:
        pass
        input1 = int(request.POST.get('input1', 0))
        input2 = int(request.POST.get('input2', 0))
        uploaded_file = request.FILES['camera_list'].read()
        uploaded_file = uploaded_file.replace(b'\r\n', b'\n')
        uploaded_file = uploaded_file.decode().split("\n")
        uploaded_file = [int(item) for item in uploaded_file if item.isdigit()]

        # filtering out any record that has snooze
        matching_records = Camera.objects.filter(camera_number__in=uploaded_file)

        # Extract the items that exist in the model
        matching_items = matching_records.values_list('camera_number', flat=True)

        # Iterate over your list and check if each item exists in the model
        good_numbers = []
        bad_numbers = []
        for item in uploaded_file:
            if item in matching_items:
                good_numbers.append(item)
            else:
                bad_numbers.append(item)

        if bad_numbers:
            message = f"Invalid camera numbers in file - {bad_numbers}"
            superuser = True
            return render(request, 'main_menu/regions.html',
                          {'message': message, 'superuser': superuser})

        camera_ids = []

        if good_numbers:
            for number in good_numbers:
                camera_object = Camera.objects.get(camera_number=number)
                # added check for snooze - principle is if snooze selected then never check anywhere,
                # if not camera_object.snooze:
                #     camera_ids.append(camera_object.id)
                camera_ids.append(camera_object.id)

        fieldnames = [
            'Camera ID',
            'focus value threshold',
            'light level threshold',
            'matching threshold',
            'schedule ID',
            'device group ID',
            'dg focus value threshold',
            'dg light level threshold',
            'dg matching threshold',
            'dg schedule id'
        ]
        synergy_csv_buffer = io.StringIO()
        synergy_writer = csv.writer(synergy_csv_buffer)
        synergy_writer.writerow(fieldnames)
        for camera_id in camera_ids:
            camera_object = Camera.objects.get(id=camera_id)

            synergy_dict = {
                'Camera ID': camera_object.camera_number,
                'focus value threshold': camera_object.focus_value_threshold,
                'light level threshold': camera_object.light_level_threshold,
                'matching threshold': camera_object.matching_threshold,
                'schedule ID': input1,
                'device group ID': input2,
                'dg focus value threshold': None,
                'dg light level threshold': None,
                'dg matching threshold': None,
                'dg schedule id': None
            }
            synergy_writer.writerow([synergy_dict[field] for field in fieldnames])
        synergy_csv_bytes = synergy_csv_buffer.getvalue().encode('utf-8')
        synergy_csv_file = io.BytesIO(synergy_csv_bytes)
        synergy_csv_file.seek(0)
        response = StreamingHttpResponse(synergy_csv_file, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="synergy.csv"'
        return response
    return render(request, "main_menu/migrate_reference_images.html")


def clear_reference_images(request):
    user_name = request.user.username
    logger.info(f"Clearing reference images accessed from user -- {request.user}")
    if request.method == "POST" and request.FILES and "input_list_for_reference_image_deletion" in request.POST:

        uploaded_file = request.FILES['camera_list'].read()
        uploaded_file = uploaded_file.replace(b'\r\n', b'\n')
        uploaded_file = uploaded_file.decode().split("\n")
        uploaded_file = [int(item) for item in uploaded_file if item.isdigit()]

        # filtering out any record that has snooze
        matching_records = Camera.objects.filter(camera_number__in=uploaded_file)

        # Extract the items that exist in the model
        matching_items = matching_records.values_list('camera_number', flat=True)

        # Iterate over your list and check if each item exists in the model
        good_numbers = []
        bad_numbers = []
        for item in uploaded_file:
            if item in matching_items:
                good_numbers.append(item)
            else:
                bad_numbers.append(item)

        if bad_numbers:
            message = f"Invalid camera numbers in file - {bad_numbers}"
            return render(request, 'main_menu/clear_reference_images.html',
                          {'message': message, })

        if good_numbers:
            camera_ids = []
            for number in good_numbers:
                camera_object = Camera.objects.get(camera_number=number)
                # added check for snooze - principle is if snooze selected then never check anywhere,
                # if not camera_object.snooze:
                camera_ids.append(camera_object.id)

        reference_images = ReferenceImage.objects.filter(url_id__in=camera_ids)

        reference_images.delete()
        message = f"Deleted {len(reference_images)} reference images"
        return render(request, 'main_menu/clear_reference_images.html', {'message': message})
    return render(request, 'main_menu/clear_reference_images.html')