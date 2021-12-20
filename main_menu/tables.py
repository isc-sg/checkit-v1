import re

import django_tables2 as tables
from django_tables2 import TemplateColumn
from .models import Camera, LogImage, EngineState


class CameraTable(tables.Table):
    last_check_date = tables.DateTimeColumn(format='d M Y, h:i A')
    url = tables.Column(verbose_name="IP Address")

    def render_url(self, value):
        return str(re.findall('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', value)).strip("[").strip("]").strip("\'")

    class Meta:
        model = Camera
        template_name = "django_tables2/bootstrap4.html"
        fields = ("camera_number", "camera_name", "camera_location", "url", "matching_threshold",
                  "last_check_date")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}


class LogTable(tables.Table):
    creation_date = tables.DateTimeColumn(format='d M Y, h:i A')
    camera_name = tables.Column(accessor='url.camera_name')
    camera_number = tables.Column(accessor='url.camera_number')
    camera_location = tables.Column(accessor='url.camera_location')
    matching_score = tables.Column()
    matching_threshold = tables.Column(accessor='url.matching_threshold')
    action = tables.Column(visible=True)
    image = tables.Column(visible=False)
    reference_image = tables.Column(accessor='url.image', visible=False)
    display_image = TemplateColumn(template_name='main_menu/display_reference_and_capture_button.html')

    class Meta:
        model = LogImage
        template_name = "django_tables2/bootstrap4.html"
        fields = ('camera_number', 'camera_name', 'camera_location', "image", "matching_score",
                  "matching_threshold", "focus_value", "action", "creation_date")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        order_by = '-creation_date'


class EngineStateTable(tables.Table):
    selection = tables.CheckBoxColumn(verbose_name="Select", accessor='pk')  # Override here to show checkbox
    state_timestamp = tables.DateTimeColumn(format='d M Y, h:i A')

    class Meta:
        model = EngineState
        template_name = 'django_tables2/bootstrap4.html'
        fields = ("state", "state_timestamp")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        sequence = ('selection', 'state', 'state_timestamp')
        order_by = '-state_timestamp'
