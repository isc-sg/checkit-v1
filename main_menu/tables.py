import cv2
import django_tables2 as tables
from django_tables2 import TemplateColumn
from .models import Camera, LogImage, EngineState, SuggestedValues, ReferenceImage
from django.utils.safestring import mark_safe
from urllib.parse import urlparse
import main_menu.select_region
import io
import base64


__version__ = 2.1


class CameraTable(tables.Table):
    camera_name = tables.Column(verbose_name="Camera Name", attrs={
        "td": {
            "width": 250, "align": "left"
        }})
    camera_location = tables.Column(verbose_name="Camera Location", attrs={
        "td": {
            "width": 250, "align": "left"
        }})
    url = tables.Column(verbose_name="IP Address", attrs={
        "td": {
            "width": 150, "align": "center"
        }})
    multicast_address = tables.Column(verbose_name="Multicast Address", attrs={
        "td": {
            "width": 150, "align": "center"
        }})
    multicast_port = tables.Column(verbose_name="Multicast Port", attrs={
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
    focus_value_threshold = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }})
    light_level_threshold = tables.Column(attrs={
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
                  "matching_threshold", "focus_value_threshold", "light_level_threshold", "last_check_date")
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
        # camera_object = Camera.objects.get(pk=record.url_id)
        # default_light_level = camera_object.light_level_threshold
        if value > record.current_light_level:
            return value
        else:
            return mark_safe(f'<span style="color: red;">{value}</span>')

    def render_focus_value(self, value, record):
        # camera_object = Camera.objects.get(pk=record.url_id)
        # default_focus_level = camera_object.focus_value_threshold
        if value > record.current_focus_value:
            return value
        else:
            return mark_safe(f'<span style="color: red;">{value}</span>')

    def render_matching_score(self, value, record):
        # camera_object = Camera.objects.get(pk=record.url_id)
        # default_matching_threshold = camera_object.matching_threshold
        if value >= record.current_matching_threshold:
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
    id = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }}, verbose_name="Run Number")
    state = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }})
    state_timestamp = tables.DateTimeColumn(attrs={'td': {"width": 580, "align": "center"}},format='d M Y, h:i A')
    number_failed_images = tables.Column(attrs={'td': {"width": 200, "align": "center"}},
                                         verbose_name="Number of images that triggered")
    number_pass_images = tables.Column(attrs={'td': {"width": 200, "align": "center"}},
                                       verbose_name="Number of pass images")
    number_others = tables.Column(attrs={'td': {"width": 200, "align": "center"}},
                                       verbose_name="Number of others")
    user = tables.Column(attrs={'td': {"width": 350, "align": "center"}},
                                  verbose_name="User ID")
    number_of_cameras_in_run = tables.Column(attrs={'td': {"width": 200, "align": "center"}},
                         verbose_name="Cameras in Run")
    progress = tables.Column(attrs={
        "td": {
            "width": 100, "align": "center"
        }}, verbose_name="Progress")

    def render_state(self, value, record):
        if record.progress < 100 and value != "Started":
            return "Not Completed"
        else:
            return value

    def render_progress(self, value):
        if value == 0:
            return ""
        else:
            return f"{int(value)}%"

    def render_id(self, value, record):
        if record.state == "STARTED":
            return " "
        else:
            return value

    def render_number_others(self, value, record):
        if record.state == "STARTED":
            return " "
        else:
            return value

    def render_number_of_cameras_in_run(self, value, record):
        if record.state == "STARTED":
            return " "
        else:
            return value

    def render_number_pass_images(self, value, record):
        if record.state == "STARTED":
            return " "
        else:
            return value

    def render_number_failed_images(self, value, column, record):
        if record.state == "STARTED":
            return " "
        else:
            if value > 0:
                return mark_safe(f'<span style="color: red;">{value}</span>')
            else:
                return value

    class Meta:
        model = EngineState
        template_name = 'django_tables2/bootstrap4.html'
        fields = ("id", "state", "state_timestamp", "number_failed_images", "number_pass_images",
                  "number_others", "number_of_cameras_in_run", "progress", "user")
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        sequence = ('selection', 'id', 'state', 'state_timestamp', 'number_failed_images',
                    'number_pass_images', 'number_others', 'number_of_cameras_in_run', 'progress', 'user')
        order_by = '-id'


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


class SuggestedValuesTable(tables.Table):
    selection = tables.CheckBoxColumn(verbose_name="Select", accessor='pk',
                                      attrs={"td": {
                                          "width": 50, "align": "center"
                                      }, "th__input": {"onclick": "toggle(this)"}})
    # new_regions = tables.Column()
    camera_number = tables.Column(empty_values=(),  attrs={
        "td": {
            "width": 100, "align": "left"
        }})
    camera_name = tables.Column(empty_values=(), attrs={
        "td": {
            "width": 250, "align": "left"
        }})
    modified_image = tables.Column(empty_values=())

    def render_camera_name(self, value, record):
        camera = Camera.objects.get(pk=record.url_id)
        return camera.camera_name

    def render_camera_number(self, value, record):
        camera = Camera.objects.get(pk=record.url_id)
        return camera.camera_number

    def render_modified_image(self, record):
        camera = ReferenceImage.objects.filter(url_id=record.url_id).last()
        ref_image = cv2.imread(f"/home/checkit/camera_checker/media/{camera.image}")
        h, w, _ = ref_image.shape
        c_list = main_menu.select_region.get_coordinates(record.new_regions, h, w)
        grid_image = main_menu.select_region.draw_grid(c_list, ref_image, h, w )
        grid_image = cv2.resize(grid_image, (int(w/2), int(h/2)))
        _, buffer = cv2.imencode('.jpg', grid_image)
        img_str = base64.b64encode(buffer).decode('utf-8')

        # Encode the image to base64
        return mark_safe(f'<img src="data:image/jpeg;base64,{img_str}"/>')

    class Meta:
        model = SuggestedValues
        template_name = "django_tables2/bootstrap4.html"
        fields = ('selection', 'camera_number', 'camera_name', 'new_matching_score',
                  'new_focus_value', 'new_light_level','modified_image')
        attrs = {'class': 'table table-striped table-bordered table-hover table-dark'}
        order_by = 'url_id'
