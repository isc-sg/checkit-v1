from django_filters import ChoiceFilter, DateRangeFilter, FilterSet, RangeFilter, NumberFilter, CharFilter
from django_filters.widgets import RangeWidget
from .models import LogImage, EngineState, Camera
from django.forms.widgets import TextInput, Textarea
from django.forms import widgets


LOG_RESULT_CHOICES = (('Pass', 'Pass'), ('Failed', 'Failed'), ('Capture Error', 'Capture Error'),
                      ('Image Size Error', 'Image Size Error'))

STATE_CHOICES = (('RUN COMPLETED', 'Finished'), ('STARTED', 'Started'), ('ERROR', 'Error'))


class CameraFilter(FilterSet):
    camera_name = CharFilter(lookup_expr='icontains')
    url = CharFilter(lookup_expr='icontains')
    camera_location = CharFilter(lookup_expr='icontains')
    matching_threshold = NumberFilter()
    last_check_date = DateRangeFilter()

    class Meta:
        model = Camera
        fields = ['camera_name', 'url', 'camera_location', 'matching_threshold', 'last_check_date']


class LogFilter(FilterSet):
    matching_score = RangeFilter(widget=RangeWidget(attrs={'size': '7'}))
    focus_value = RangeFilter(widget=RangeWidget(attrs={'size': '7'}))
    action = ChoiceFilter(choices=LOG_RESULT_CHOICES)
    creation_date = DateRangeFilter()
    camera_name = CharFilter(field_name='url__camera_name', lookup_expr='icontains', label="Camera name contains",
                             widget=TextInput(attrs={'size': '13'}))
    camera_number = CharFilter(field_name='url__camera_number', lookup_expr='icontains', label="Camera number contains",
                               widget=TextInput(attrs={'size': '13'}))
    camera_location = CharFilter(field_name='url__camera_location', lookup_expr='icontains',
                                 label="Camera location contains",
                                 widget=TextInput(attrs={'size': '13'}))

    class Meta:
        model = LogImage
        fields = ["camera_number", "camera_name", "camera_location", "matching_score", "focus_value",
                  "action", "creation_date"]


class EngineStateFilter(FilterSet):
    state = ChoiceFilter(choices=STATE_CHOICES)
    state_timestamp = DateRangeFilter()
    number_failed_images = RangeFilter(widget=RangeWidget(attrs={'size': '7'},), label="Number of fails")

    class Meta:
        model = EngineState
        fields = ['state', 'state_timestamp', "number_failed_images"]
