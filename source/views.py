import datetime
import subprocess
import csv
import os
import io
import base64
import logging
from logging.handlers import RotatingFileHandler
from bisect import bisect_left
import cv2
import numpy as np

from django.http import HttpResponse, HttpResponseRedirect, FileResponse
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

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

error_image = np.zeros((720, 1280, 3), np.uint8)

error_image = cv2.putText(error_image, "Error retrieving image",
                              (250, 300), cv2.FONT_HERSHEY_TRIPLEX, 2,
                              (0, 0, 255), 2, cv2.LINE_AA)


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


def index(request):
    # user_name = request.user.username
    # logging.info("User {u} access to System Status".format(u=user_name))
    template = loader.get_template('main_menu/dashboard.html')
    obj = EngineState.objects.last()
    if obj is not None:
        state = obj.state
        context = {'system_state': state}
    else:
        context = {'system_state': "RUN COMPLETED"}
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
    user_name = request.user.username
    logging.info("User {u} access to Scheduler".format(u=user_name))

    template = loader.get_template('main_menu/scheduler.html')
    # get the actual state from the engine here and pass it to context
    obj = EngineState.objects.last()
    if obj is not None:
        state = obj.state
    else:
        state = "RUN COMPLETED"
    license_obj = Licensing.objects.last()
    run_schedule = license_obj.run_schedule
    context = {'system_state': state, 'run_schedule': run_schedule}

    # can use pid method to check if actually running. see compare_images_v2

    if request.method == 'POST' and 'start_engine' in request.POST:
        logging.info("User {u} started engine".format(u=user_name))
        # subprocess.Popen(["nohup", "/home/checkit/camera_checker/main_menu/compare_images_v2.bin"])
        process_output = subprocess.check_output(["/home/checkit/env/bin/python",
                                                  "/home/checkit/camera_checker/main_menu/start.py"])
        if process_output.decode() == '':
            process_output = "Run Completed - No errors reported"
        logging.info("Process Output {p}".format(p=process_output))

        return HttpResponseRedirect(reverse(index))
    if request.method == 'POST' and 'new_run' in request.POST:
        new_run_schedule = request.POST.get('new_run')
        old_run_schedule = license_obj.run_schedule
        if new_run_schedule != old_run_schedule:
            license_obj.run_schedule = new_run_schedule
            license_obj.save()
            if int(new_run_schedule) == 0:
                command = "/usr/bin/crontab -r"
                logging.info("User {u} set scheduler to not running".format(u=user_name))
            else:

                # command = "/bin/echo 0 \*" + "/" + new_run_schedule + \
                #           " \* \* \* /home/checkit/camera_checker/main_menu/compare_images_v2.bin | crontab -"
                if int(new_run_schedule) < 24:
                    command = "/bin/echo 0 *" + "/" + new_run_schedule + \
                              " \* \* \* /home/checkit/env/bin/python " \
                              "/home/checkit/camera_checker/main_menu/start.py | crontab -"
                else:
                    command = "/bin/echo 0 0 \* \* \* /home/checkit/env/bin/python " \
                              "/home/checkit/camera_checker/main_menu/start.py | crontab -"
            subprocess.Popen(command, shell=True)
            logging.info(f"User {user_name} modified run schedule to {new_run_schedule}"
                         f" hours from {old_run_schedule} hours")
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
        # process_output = subprocess.check_output(["/home/checkit/camera_checker/main_menu/compare_images_v2.bin",
        #                                           camera_number])
        process_output = subprocess.check_output(["/home/checkit/env/bin/python",
                                                  "/home/checkit/camera_checker/main_menu/start.py", camera_number])
        logging.info(f"User {user_name} completed camera check for camera {camera_number}")
        if process_output.decode() == '':
            process_output = "Run Completed - No errors reported"
        logging.info("Process Output {p}".format(p=process_output))
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
    paginate_by = 24
    filterset_class = EngineStateFilter
    ordering = 'state_timestamp'


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
            for log in logs:
                if log.action == "Failed":
                    camera_name = log.url.camera_name
                    camera_number = log.url.camera_number
                    hour = str(log.creation_date.hour).zfill(2)
                    log_image = settings.MEDIA_ROOT + "/" + str(log.image)
                    camera = Camera.objects.filter(id=log.url_id)
                    # print(camera)
                    for c in camera:
                        base_image = settings.MEDIA_ROOT + "/base_images/" + str(c.id) + "/" + hour + ".jpg"
                    matching_score = log.matching_score
                    image_list.append((camera_name, camera_number, log.creation_date, base_image, matching_score,
                                       log.action, log_image))
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)

            page_width, page_height = A4
            if image_list:
                while len(image_list) > 0:
                    left_margin_pos = 20
                    top_margin_text_pos = 25
                    top_margin_image_pos = 70
                    second_image_pos = 90
                    count = 0
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
                    c.drawString(*coord(60, 10, page_height, mm),
                                 text="Failed Images Report")
                    # c.line(*coord(60, 12, page_height, mm), *coord(125, 12, page_height, mm))
                    c.setFont("Helvetica", 10)
                    c.drawString(*coord(180, 10, page_height, mm),
                                 text="Page " + str(c.getPageNumber()))
                    for i in image_list[:4]:
                        # print(i)
                        camera_name, camera_number, creation_time, base_image, matching_score, log.action, log_image = i
                        creation_time = creation_time

                        c.drawString(
                            *coord(left_margin_pos, top_margin_text_pos + (count * top_margin_image_pos) - 5, page_height,
                                   mm),
                            text=camera_name + " - Camera Number: " + str(camera_number))

                        c.drawString(
                            *coord(left_margin_pos, top_margin_text_pos + (count * top_margin_image_pos), page_height, mm),
                            text="Time: " + creation_time.strftime("%d-%b-%Y %H:%M:%S"))
                        c.drawString(
                            *coord(left_margin_pos + 90, top_margin_text_pos + (count * top_margin_image_pos), page_height,
                                   mm),
                            text="Matching Score: " + str(matching_score))

                        image_rl = canvas.ImageReader(base_image)
                        image_width, image_height = image_rl.getSize()
                        scaling_factor = image_width / page_width
                        c.setLineWidth(2)
                        c.setStrokeColor(HexColor("#b9b6a9"))
                        c.roundRect(left_margin_pos + 11,
                                    page_height - (top_margin_image_pos + (count * top_margin_image_pos * mm)) - 139,
                                    width=518, height=168, radius=4, stroke=1, fill=0)
                        c.setStrokeColor(HexColor("#767368"))
                        c.roundRect(left_margin_pos + 10,
                                    page_height - (top_margin_image_pos + (count * top_margin_image_pos * mm)) - 140,
                                    width=520, height=170, radius=4, stroke=1, fill=0)
                        c.drawImage(image_rl,
                                    *coord(left_margin_pos, top_margin_image_pos + (count * top_margin_image_pos),
                                           page_height, mm),
                                    width=image_width / (mm * scaling_factor),
                                    height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)
                        image_rl2 = canvas.ImageReader(log_image)
                        image_width, image_height = image_rl.getSize()

                        c.drawImage(image_rl2,
                                    *coord(left_margin_pos + second_image_pos,
                                           top_margin_image_pos + (count * top_margin_image_pos),
                                           page_height, mm), width=image_width / (mm * scaling_factor),
                                    height=image_height / (mm * scaling_factor), preserveAspectRatio=True, mask=None)

                        count += 1
                    c.showPage()
                    del image_list[:4]
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
        return HttpResponseRedirect("/state")


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
            context = {
                'form': form,
                'camera_number': camera_number,
                'image': base64_image
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
        if form.is_valid():
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
                context = {
                    'form': form,
                    'camera_number': camera_number,
                    'image': base64_image
                }
                return render(request, 'main_menu/regions_main_form.html', context=context)

    else:
        message = ""
        return render(request, 'main_menu/regions.html', {'message': message})
