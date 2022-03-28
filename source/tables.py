import re

import django_tables2 as tables
from django_tables2 import TemplateColumn
from django.utils.html import format_html
from .models import Camera, LogImage, EngineState


class CameraTable(tables.Table):
    url = tables.Column(verbose_name="IP Address", attrs={
        "td": {
            "width": 150, "align": "center"
        }})
    multicast_address = tables.Column(verbose_name="Multicast Address", attrs={
        "td": {
            "width": 150, "align": "center"
        }})
    camera_number = tables.Column(attrs={
        "td": {
            "width": 150, "align": "center"
        }})
    matching_threshold = tables.Column(attrs={
        "td": {
            "width": 200, "align": "center"
        }})
    last_check_date = tables.DateTimeColumn(format='d M Y, h:i A', attrs={
        "td": {
            "width": 200, "align": "left"
        }})


    def render_url(self, value):
        return str(re.findall('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', value)).strip("[").strip("]").strip("\'")

    class Meta:
        model = Camera
        template_name = "django_tables2/bootstrap4.html"
        fields = ("camera_number", "camera_name", "camera_location", "url", "multicast_address", "matching_threshold",
                  "last_check_date")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}


class LogTable(tables.Table):
    creation_date = tables.DateTimeColumn(format='d M Y, h:i A', attrs={
        "td": {
            "width": 200, "align": "left"
        }})
    camera_name = tables.Column(accessor='url.camera_name')

    camera_number = tables.Column(accessor='url.camera_number', attrs={
        "td": {
            "width": 100, "align": "center"
        }})
    camera_location = tables.Column(accessor='url.camera_location')

    matching_score = tables.Column(attrs={
        "td": {
            "width": 140, "align": "center"
        }})

    focus_value = tables.Column(attrs={
        "td": {
            "width": 140, "align": "center"
        }})

    matching_threshold = tables.Column(accessor='url.matching_threshold')

    action = tables.Column(visible=True, verbose_name="Status", attrs={
        "td": {
            "width": 150, "align": "center"
        }})

    image = tables.Column(visible=False)
    reference_image = tables.Column(accessor='url.image', visible=False)
    display_image = TemplateColumn(template_name='main_menu/display_reference_and_capture_button.html', attrs={
        "td": {
            "width": 150, "align": "center"
        }})

    class Meta:
        model = LogImage
        template_name = "django_tables2/bootstrap4.html"
        fields = ('camera_number', 'camera_name', 'camera_location', 'image', 'matching_score',
                  'focus_value', 'action', 'creation_date')
        exclude = (['matching_threshold'])
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        order_by = '-creation_date'


class EngineStateTable(tables.Table):
    selection = tables.CheckBoxColumn(verbose_name="Select", accessor='pk',
                                      attrs={"td": {
                                             "width": 50, "align": "center"
                                             }, "th__input": {"onclick": "toggle(this)"}})
    state = tables.Column(attrs={
        "td": {
            "width": 150, "align": "center"
        }})
    state_timestamp = tables.DateTimeColumn(format='d M Y, h:i A')
    number_failed_images = tables.Column(verbose_name="Number of failed images")

    def render_number_failed_images(self, value, column):
        if value > 0:
            column.attrs = {'td': {'bgcolor': '#5603ad', "width": 200, "align": "center"}}
        else:
            column.attrs = {'td': {"width": 200, "align": "center"}}
        return value

    class Meta:
        model = EngineState
        template_name = 'django_tables2/bootstrap4.html'
        fields = ("state", "state_timestamp", "number_failed_images")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        sequence = ('selection', 'state', 'state_timestamp', 'number_failed_images')
        order_by = '-state_timestamp'
