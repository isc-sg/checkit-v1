import django_tables2 as tables
from django_tables2 import TemplateColumn
from .models import Camera, LogImage, EngineState
from django.utils.safestring import mark_safe
from urllib.parse import urlparse


class CameraTable(tables.Table):
    camera_name = tables.Column(verbose_name="Camera Name", attrs={
        "td": {
            "width": 180, "align": "left"
        }})
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
            "width": 120, "align": "center"
        }})
    matching_threshold = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }})
    last_check_date = tables.DateTimeColumn(format='d M Y, h:i A', attrs={
        "td": {
            "width": 200, "align": "left"
        }})

    def render_url(self, value):
        details = urlparse(value)
        return details.hostname
        # return str(re.findall('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', value)).strip("[").strip("]").strip("\'")

    def render_multicast_port(self, value):
        if value == 0:
            return "—"
        else:
            return value

    class Meta:
        model = Camera
        template_name = "django_tables2/bootstrap4.html"
        fields = ("camera_number", "camera_name", "camera_location", "url", "multicast_address", "multicast_port",
                  "matching_threshold", "last_check_date")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}


class LogTable(tables.Table):
    creation_date = tables.DateTimeColumn(format='d M Y, h:i A', attrs={
        "td": {
            "width": 200, "align": "left"
        }})
    camera_name = tables.Column(accessor='url.camera_name', attrs={
        "td": {
            "width": 180, "align": "left"
        }})

    camera_number = tables.Column(accessor='url.camera_number', attrs={
        "td": {
            "width": 100, "align": "center"
        }})
    camera_location = tables.Column(accessor='url.camera_location')

    matching_score = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }})

    focus_value = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }})
    light_level = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }})
    # region_scores = tables.Column(verbose_name="Region Analysis", attrs={
    #     "td": {
    #         "width": 140, "align": "center"
    #     }})

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

    def render_light_level(self, value, record):
        camera_object = Camera.objects.get(pk=record.url_id)
        default_light_level = camera_object.light_level_threshold
        if value > default_light_level:
            return value
        else:
            return mark_safe(f'<span style="color: red;">{value}</span>')

    def render_focus_value(self, value, record):
        camera_object = Camera.objects.get(pk=record.url_id)
        default_focus_level = camera_object.focus_value_threshold
        if value > default_focus_level:
            return value
        else:
            return mark_safe(f'<span style="color: red;">{value}</span>')

    def render_matching_score(self, value, record):
        camera_object = Camera.objects.get(pk=record.url_id)
        default_matching_threshold = camera_object.matching_threshold
        if value >= default_matching_threshold:
            return value
        else:
            return mark_safe(f'<span style="color: red;">{value}</span>')

    def render_action(self, value):
        if value == "Pass":
            return mark_safe(f'<span style="color: green;">{value}</span>')
        else:
            return mark_safe(f'<span style="color: red;">{value}</span>')

    def render_region_scores(self, value):
        try:
            sorted_keys = sorted(value, key=value.get)
        except TypeError:
            sorted_keys = []
        display = "Low " + ','.join(str(y) for y in sorted_keys[:8]) + " - " + "High " +\
                  ','.join(str(y) for y in sorted_keys[-8:])
        return display

    class Meta:
        model = LogImage
        template_name = "django_tables2/bootstrap4.html"
        fields = ('camera_number', 'camera_name', 'camera_location', 'image', 'matching_score',
                  'focus_value', 'light_level', 'action', 'creation_date',)
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
    state_timestamp = tables.DateTimeColumn(attrs={'td': {"width": 230, "align": "center"}},format='d M Y, h:i A')
    number_failed_images = tables.Column(verbose_name="Number of failed images")
    number_pass_images = tables.Column(attrs={'td': {"width": 200, "align": "center"}},
                                       verbose_name="Number of pass images")

    def render_number_failed_images(self, value, column):
        if value > 0:
            column.attrs = {'td': {'bgcolor': '#770000', "width": 200, "align": "center"}}
        else:
            column.attrs = {'td': {"width": 200, "align": "center"}}
        return value


    class Meta:
        model = EngineState
        template_name = 'django_tables2/bootstrap4.html'
        fields = ("state", "state_timestamp", "number_failed_images", "number_pass_images")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        sequence = ('selection', 'state', 'state_timestamp', 'number_failed_images', 'number_pass_images')
        order_by = '-state_timestamp'


class CameraSelectTable(tables.Table):
    selection = tables.CheckBoxColumn(verbose_name="Select", accessor='pk',
                                      attrs={"td": {
                                             "width": 50, "align": "center"
                                             }, "th__input": {"onclick": "toggle(this)"}})
    camera_name = tables.Column(attrs={
        "td": {
            "width": 150, "align": "center"
        }})
    camera_number = tables.Column(attrs={
        "td": {
            "width": 150, "align": "center"
        }})

    class Meta:
        model = Camera
        template_name = 'django_tables2/bootstrap4.html'
        fields = ('camera_name', 'camera_number', 'camera_number', 'url', 'multicast_address',
                  'multicast_port', 'matching_threshold', 'focus_value_threshold', 'light_level_threshold')
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        sequence = ('selection', 'camera_name', 'camera_number', 'url', 'multicast_address',
                    'multicast_port', 'matching_threshold', 'focus_value_threshold', 'light_level_threshold')
        order_by = 'camera_number'

class LogSummaryTable(tables.Table):
    action = tables.Column()
    hour = tables.Column()
    count = tables.Column()
    class Meta:
        model = LogImage
        template_name = "django_tables2/bootstrap4.html"
        fields = ('hour', 'action', 'count')
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        order_by = '-hour'
