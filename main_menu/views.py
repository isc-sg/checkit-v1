import datetime
import time
import subprocess
import csv
import os
import base64
import logging

import cv2
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from django.shortcuts import render, reverse, redirect
from tablib import Dataset
from django_tables2 import SingleTableMixin
from django_filters.views import FilterView
from django.core.exceptions import *
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.views.decorators.cache import cache_control

from .resources import CameraResource
from .models import EngineState, Camera, LogImage, Licensing, ReferenceImage
from .tables import CameraTable, LogTable, EngineStateTable
from .forms import DateForm, RegionsForm
from .filters import CameraFilter, LogFilter, EngineStateFilter
import main_menu.select_region as select_region


logging.basicConfig(filename='/tmp/checkit.log', format='%(asctime)s %(message)s', level=logging.INFO)


def index(request):
    # user_name = request.user.username
    # logging.info("User {u} access to System Status".format(u=user_name))
    template = loader.get_template('main_menu/dashboard.html')
    obj = EngineState.objects.last()
    state = obj.state
    context = {'system_state': state}
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
            context = {'capture_image': obj.image, 'reference_image': image, 'result': result,
                       'camera_name': camera_name, 'camera_number': camera_number}
        else:
            context = {'result': result, 'camera_name': camera_name}
        return HttpResponse(template.render(context, request))
    else:
        return redirect('logs')


@permission_required('camera_checker.main_menu')
def scheduler(request):
    # user_name = request.user.username
    # logging.info("User {u} access to Scheduler".format(u=user_name))

    template = loader.get_template('main_menu/scheduler.html')
    # get the actual state from the engine here and pass it to context
    obj = EngineState.objects.last()
    state = obj.state
    license_obj = Licensing.objects.last()
    run_schedule = license_obj.run_schedule
    context = {'system_state': state, 'run_schedule': run_schedule}

    # can use pid method to check if actually running. see compare_images_v2

    if request.method == 'POST' and 'start_engine' in request.POST:
        subprocess.Popen(["nohup", "/home/checkit/camera_checker/main_menu/compare_images_v2.bin"])
        # logging.info("User {u} started engine".format(u=user_name))
        time.sleep(5)
        return HttpResponseRedirect(reverse(scheduler))
    if request.method == 'POST' and 'new_run' in request.POST:
        new_run_schedule = request.POST.get('new_run')
        if new_run_schedule != license_obj.run_schedule:
            license_obj.run_schedule = new_run_schedule
            license_obj.save()
            if int(new_run_schedule) == 0:
                command = "/usr/bin/crontab -r"
                # logging.info("User {u} set scheduler to not running".format(u=user_name))
            else:

                command = "/bin/echo 0 \*" + "/" + new_run_schedule + \
                          " \* \* \* /home/checkit/camera_checker/main_menu/compare_images_v2.bin | crontab -"
                # TODO - check crontab -l to see if this line worked
            subprocess.Popen(command, shell=True)
            # logging.info("User {u} started engine".format(u=user_name))
        return HttpResponseRedirect(reverse(scheduler))
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
        process_output = subprocess.check_output(["/home/checkit/camera_checker/main_menu/compare_images_v2.bin",
                                                  camera_number])
        # user_name = request.user.username
        # logging.info("User {u} completed camera check for camera {c}".format(u=user_name, c=camera_number))
        # logging.info(process_output)
        time.sleep(5)
        return HttpResponseRedirect(reverse(index))
    return HttpResponse(template.render(context, request))


@login_required
def licensing(request):
    # user_name = request.user.usename
    # logging.info("User {u} access to Licensing".format(u=user_name))
    template = loader.get_template('main_menu/license.html')
    # get the actual state from the engine here and pass it to context
    obj = Licensing.objects.last()
    start_date = obj.start_date
    start_date = datetime.datetime.strftime(start_date, "%d-%B-%Y")
    end_date = obj.end_date
    end_date = datetime.datetime.strftime(end_date, "%d-%B-%Y")
    transaction_limit = obj.transaction_limit
    transaction_count = obj.transaction_count
    license_owner = obj.license_owner
    site_name = obj.site_name
    context = {'start_date': start_date, 'end_date': end_date, 'site_name': site_name,
               'transaction_limit': transaction_limit, 'license_owner': license_owner,
               'transaction_count': transaction_count}
    return HttpResponse(template.render(context, request))


class CameraView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Camera
    table_class = CameraTable
    template_name = 'main_menu/camera_table.html'
    paginate_by = 18
    filterset_class = CameraFilter
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
        form = DateForm()

    return render(request, '/main_menu/date.html', {'form': form})


class EngineStateView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = EngineState
    table_class = EngineStateTable
    template_name = 'main_menu/engine_state_table.html'
    paginate_by = 18
    filterset_class = EngineStateFilter
    ordering = 'state_timestamp'


def export_logs_to_csv(request):
    selection = request.POST.getlist("selection")
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="result_export.csv"'},
    )
    # log_index = int(selection[0])
    # prev_log_index = log_index - 1
    # end = EngineState.objects.get(id=log_index).state_timestamp
    # start = EngineState.objects.get(id=prev_log_index).state_timestamp
    # logs = LogImage.objects.filter(creation_date__range=(start, end))
    # for i in selection:
    #     count += 1
    writer = csv.writer(response)

    for i in selection:
        log_index = int(i)
        prev_log_index = log_index - 1
        end = EngineState.objects.get(id=log_index).state_timestamp
        start = EngineState.objects.get(id=prev_log_index).state_timestamp
        state = EngineState.objects.get(id=prev_log_index).state
        first_record = EngineState.objects.first().id

        while state != "STARTED" and prev_log_index > (int(first_record) + 1):
            prev_log_index = prev_log_index - 1
            try:
                start = EngineState.objects.get(id=prev_log_index).state_timestamp
            except ObjectDoesNotExist:
                writer.writerow(["Error in retrieving start time for selected run id ", log_index])
                break

        logs = LogImage.objects.filter(creation_date__range=(start, end))
        writer.writerow(["camera_name", "camera_number", "camera_location",
                         "url", "matching_score", "focus_value", "creation_date"])
        for log in logs:
            writer.writerow([log.url.camera_name, log.url.camera_number, log.url.camera_location,
                             log.url.url, log.matching_score, log.focus_value, log.creation_date])

    return response


@permission_required('camera_checker.main_menu')
def display_image_in_page_from_memory(request, camera_number):
    try:
        camera_object = Camera.objects.get(camera_number=camera_number)
    except ObjectDoesNotExist as error:
        form = RegionsForm()
        camera_number = "<h1 style=\"color: #FFFFFF\">Camera not found</h1>"
        return HttpResponse(camera_number)
        # return render(request, 'main_menu/regions.html', {'form': form, 'camera_number': camera_number})
    else:
        time_stamp = datetime.datetime.now()
        hour = time_stamp.strftime('%H')

        reference_images = ReferenceImage.objects.filter(url_id=camera_object.id)
        if reference_images:
            hours = []
            # TODO: need error checking if there are no reference images
            for record in reference_images:
                hours.append(record.hour)
            for i in range(0, len(hours)):
                hours[i] = int(hours[i])
            hour = int(hour)
            absolute_difference_function = lambda list_value: abs(list_value - hour)
            closest_hour = min(hours, key=absolute_difference_function)
            closest_hour = str(closest_hour).zfill(2)

            reference_images = ReferenceImage.objects.get(url_id=camera_object.id, hour=closest_hour)
            image = reference_images.image
            img = cv2.imread(os.path.join(settings.MEDIA_ROOT, str(image)))
            regions = camera_object.image_regions
            regions = eval(regions)
            height, width, channels = img.shape

            co_ordinates = select_region.get_coordinates(regions, height, width)

            image = select_region.draw_grid(co_ordinates, img, height, width)
            img_cv2_converted_to_string = cv2.imencode('.jpg', image)[1]
            image_base64 = base64.b64encode(img_cv2_converted_to_string).decode('utf-8')
            data_uri = 'data:image/jpg;base64,'
            data_uri += str(image_base64)
            img_string = "<img src=" + "\"" + data_uri + "\"" + "/>"
            return HttpResponse(img_string)
        else:
            camera_number = "<h1 style=\"color: #FFFFFF\">No Reference Images</h1>"
            return HttpResponse(camera_number)


@permission_required('camera_checker.main_menu')
def display_image_grid_regions(request):
    template = loader.get_template('main_menu/regions.html')
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = RegionsForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            if 'camera_number' in request.POST and "returned_number" not in request.POST:
                try:
                    camera_number = request.POST.get('camera_number')
                except ObjectDoesNotExist:
                    return render(request, 'main_menu/regions.html', {'form': form})
                else:
                    return render(request, 'main_menu/regions.html', {'form': form, 'camera_number': camera_number})
            else:
                regions = form.cleaned_data['regions']
                camera_number = request.POST.get('returned_number')
                camera_object = Camera.objects.get(camera_number=camera_number)
                camera_object.image_regions = regions
                camera_object.save()
                # template = loader.get_template('main_menu/saved.html')
                return render(request, 'main_menu/regions.html', {'form': form, 'camera_number': camera_number})

    # if a GET (or any other method) we'll create a blank form
    else:
        form = RegionsForm()

    return render(request, 'main_menu/regions.html', {'form': form})
