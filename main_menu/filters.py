from django_filters import (ChoiceFilter, DateRangeFilter, FilterSet, RangeFilter,
                            NumberFilter, CharFilter, DateFromToRangeFilter, Filter)
from django_filters.widgets import RangeWidget, DateRangeWidget

from .models import LogImage, EngineState, Camera
from django.forms.widgets import TextInput, NumberInput, SplitDateTimeWidget
from django.forms import widgets
from bootstrap_datepicker_plus.widgets import DatePickerInput, DateTimePickerInput
from datetime import datetime
from django.db.models import Q

__version__ = 2.1


LOG_RESULT_CHOICES = (('Pass', 'Pass'), ('Triggered', 'Triggered'), ('Capture Error', 'Capture Error'),
                      ('Skipped', 'Skipped'), ('Reference Captured', 'Reference Captured'),
                      ('Image Size Error', 'Image Size Error'))

STATE_CHOICES = (('RUN COMPLETED', 'Finished'), ('STARTED', 'Started'), ('ERROR', 'Error'))


class CameraFilter(FilterSet):
    camera_name = CharFilter(lookup_expr='icontains',
                             widget=TextInput(attrs={'size': '15'}), label="Name contains")
    camera_number = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))
    multicast_address = CharFilter(lookup_expr='icontains',
                             widget=TextInput(attrs={'size': '15'}), label="Multicast Address contains")
    url = CharFilter(lookup_expr='icontains',
                     widget=TextInput(attrs={'size': '14'}), label="URL contains")
    camera_location = CharFilter(lookup_expr='icontains',
                                 widget=TextInput(attrs={'size': '18'}), label="Location contains")
    matching_threshold = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))
    focus_value_threshold = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))
    light_level_threshold = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))
    last_check_date = DateRangeFilter()

    class Meta:
        model = Camera
        fields = ['camera_number', 'camera_name', 'multicast_address', 'url', 'camera_location', 'matching_threshold',
                  'focus_value_threshold', 'light_level_threshold', 'last_check_date']


class CameraSelectFilter(FilterSet):
    camera_name = CharFilter(lookup_expr='icontains',
                             widget=TextInput(attrs={'size': '15'}), label="Name contains")
    url = CharFilter(lookup_expr='icontains',
                     widget=TextInput(attrs={'size': '14'}), label="URL contains")
    camera_location = CharFilter(lookup_expr='icontains',
                                 widget=TextInput(attrs={'size': '18'}), label="Location contains")
    camera_number = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))
    matching_threshold = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))
    focus_value_threshold = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))
    light_level_threshold = NumberFilter(widget=NumberInput(attrs={'style': 'width:23ch'}))

    class Meta:
        model = Camera
        fields = ['camera_name', 'camera_number', 'url', 'camera_location', 'matching_threshold', 'last_check_date']


class TimeRangeFilter(Filter):
    def filter(self, qs, value):
        # Ensure the value is a list with the correct format
        if value and isinstance(value, list) and len(value) == 2:
            start_time_str, end_time_str = value
            # Check if start_time_str and end_time_str are not None
            if start_time_str and end_time_str:
                try:
                    start_time = datetime.strptime(start_time_str, "%H:%M").time()
                    end_time = datetime.strptime(end_time_str, "%H:%M").time()

                    # Return the filtered queryset based on the time range
                    return qs.filter(
                        Q(creation_date__time__gte=start_time) & Q(creation_date__time__lte=end_time)
                    )
                except ValueError:
                    # Handle invalid time formats gracefully
                    pass
        return qs

class LogFilter(FilterSet):
    matching_score = RangeFilter(widget=RangeWidget(attrs={'size': '12'}), label="Match")
    focus_value = RangeFilter(widget=RangeWidget(attrs={'size': '12'}), label="Focus")
    light_level = RangeFilter(widget=RangeWidget(attrs={'size': '12'}), label="Light")
    action = ChoiceFilter(choices=LOG_RESULT_CHOICES)

    # Date and time range fields for filtering separately
    creation_date = DateFromToRangeFilter(widget=RangeWidget(attrs={'type': 'date'}))
    creation_time = TimeRangeFilter(widget=RangeWidget(attrs={'type': 'time'}))

    camera_name = CharFilter(field_name='url__camera_name', lookup_expr='icontains', label="Name contains",
                             widget=TextInput(attrs={'size': '15'}))
    camera_number = CharFilter(field_name='url__camera_number', lookup_expr='icontains', label="Number contains",
                               widget=TextInput(attrs={'size': '18'}))
    camera_location = CharFilter(field_name='url__camera_location', lookup_expr='icontains',
                                 label="Location contains",
                                 widget=TextInput(attrs={'size': '18'}))
    run_number = CharFilter(field_name='run_number', label="Run number",
                            widget=TextInput(attrs={'size': '18'}))

    # Custom filter method to handle both date and time together
    def filter_creation_datetime(self, queryset, name, value):
        date_range = self.form.cleaned_data.get('creation_date')
        time_range = self.form.cleaned_data.get('creation_time')

        if date_range and time_range:
            try:
                # Combine date and time ranges
                start_datetime = datetime.combine(date_range.start, time_range.start)
                end_datetime = datetime.combine(date_range.stop, time_range.stop)
                return queryset.filter(creation_date__range=(start_datetime, end_datetime))
            except AttributeError:
                pass  # Ignore if any part is missing or invalid
        return queryset

    class Meta:
        model = LogImage
        fields = ["camera_number", "camera_name", "camera_location", "matching_score", "focus_value", "light_level",
                  "run_number", "action", "creation_date", "creation_time"]

class EngineStateFilter(FilterSet):
    state = ChoiceFilter(choices=STATE_CHOICES)
    state_timestamp = DateRangeFilter()
    number_failed_images = RangeFilter(widget=RangeWidget(attrs={'size': '7'},), label="Fails")
    number_pass_images = RangeFilter(widget=RangeWidget(attrs={'size': '7'},), label="Pass")
    user = CharFilter(field_name='user', lookup_expr='icontains', label="User contains",
                             widget=TextInput(attrs={'size': '15'}))
    class Meta:
        model = EngineState
        fields = ['state', 'state_timestamp', "number_failed_images", "number_pass_images", "user"]
