import datetime
import os.path

from django.db import models
from django.core import validators
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.forms.fields import URLField as FormURLField
from django.utils import timezone
from django.utils.timezone import now
from django.urls import reverse
from django.template.defaultfilters import slugify
from simple_history.models import HistoricalRecords
import shutil
from django_filters import ChoiceFilter, DateRangeFilter, FilterSet, NumberFilter, CharFilter, NumericRangeFilter

LOG_RESULT_CHOICES = (('Pass', 'Pass'), ('Failed', 'Failed'), ('Capture Error', 'Capture Error'),
                      ('Image Size Error', 'Image Size Error'))
STATE_CHOICES = (('RUN COMPLETED', 'Finished'), ('STARTED', 'Started'), ('ERROR', 'Error'))


class CameraURLFormField(FormURLField):
    default_validators = [RegexValidator('^((http:|https:|rtsp:)\/\/'
                                         '(.+:.+@)?(((?:(?:2(?:[0-4][0-9]|5[0-5])|'
                                         '[0-1]?[0-9]?[0-9])\.){3}(?:(?:2([0-4][0-9]|5[0-5])|[0-1]?[0-9]?[0-9]))))'
                                         '+(:\d+)?(\/.+)*)$')]


class CameraURLField(models.URLField):
    default_validators = [RegexValidator('^((http:|https:|rtsp:)\/\/'
                                         '(.+:.+@)?(((?:(?:2(?:[0-4][0-9]|5[0-5])|'
                                         '[0-1]?[0-9]?[0-9])\.){3}(?:(?:2([0-4][0-9]|5[0-5])|[0-1]?[0-9]?[0-9]))))'
                                         '+(:\d+)?(\/.+)*)$')]

    def formfield(self, **kwargs):
        return super(CameraURLField, self).formfield(**{
            'form_class': CameraURLFormField,
        })


class DaysOfWeek(models.Model):

    # DAY_MONDAY = 'Monday'
    # DAY_TUESDAY = 'Tuesday'
    # DAY_WEDNESDAY = 'Wednesday'
    # DAY_THURSDAY = 'Thursday'
    # DAY_FRIDAY = 'Friday'
    # DAY_SATURDAY = 'Saturday'
    # DAY_SUNDAY = 'Sunday'
    # DAYS_CHOICES = [(DAY_MONDAY, 'Monday'),
    #                 (DAY_TUESDAY, 'Tuesday'),
    #                 (DAY_WEDNESDAY, 'Wednesday'),
    #                 (DAY_THURSDAY, 'Thursday'),
    #                 (DAY_FRIDAY, 'Friday'),
    #                 (DAY_SATURDAY, 'Saturday'),
    #                 (DAY_SUNDAY, 'Sunday')]
    day_of_the_week = models.CharField("Days in the week", max_length=12)

    def __str__(self):
        return self.day_of_the_week


class HoursInDay(models.Model):
    hour_in_the_day = models.IntegerField("Hours in the Day")

    def __str__(self):
        return str(self.hour_in_the_day)


class Camera(models.Model):
    url = models.CharField(max_length=255, unique=True, verbose_name="Camera URL")
    multicast_address = models.GenericIPAddressField(protocol='IPv4', blank=True, null=True, unique=True, default=None)
    multicast_port = models.IntegerField(blank=True, default=0, null=True,
                                         validators=[MaxValueValidator(65535), MinValueValidator(0)])
    camera_username = models.CharField(max_length=32, blank=True, verbose_name="Username")
    camera_password = models.CharField(max_length=64, blank=True, verbose_name="Password")
    # image = models.ImageField(upload_to='base_images/')
    camera_number = models.IntegerField(null=False, blank=False, unique=True,
                                        validators=[MaxValueValidator(9999999999), MinValueValidator(1)])
    camera_name = models.CharField(max_length=100, null=False, blank=False, unique=True)
    slug = models.SlugField(max_length=100, null=True, blank=False, unique=True, verbose_name="URL friendly name")
    camera_location = models.CharField(max_length=100)
    image_regions = models.CharField(max_length=300, default="[]")
    matching_threshold = models.DecimalField(max_digits=3, decimal_places=2,
                                             validators=[MaxValueValidator(1), MinValueValidator(0)],
                                             default=0.5)
    focus_value_threshold = models.DecimalField(max_digits=6, decimal_places=2,
                                                validators=[MaxValueValidator(9999), MinValueValidator(0)],
                                                default=0.5)
    light_level_threshold = models.DecimalField(max_digits=5, decimal_places=2,
                                                validators=[MaxValueValidator(255), MinValueValidator(0)],
                                                default=80)
    creation_date = models.DateTimeField('date created', default=timezone.now)
    last_check_date = models.DateTimeField('date checked', default=timezone.now)
    scheduled_hours = models.ManyToManyField(HoursInDay, blank=True, help_text="List format 0-23")
    scheduled_days = models.ManyToManyField(DaysOfWeek, blank=True, help_text="List format 1-7")
    snooze = models.BooleanField(default=False,help_text="Set to true to pause checks for this camera")
    trigger_new_reference_image = models.BooleanField(default=False, help_text="Set to true to enable the initiation"
                                                                               " of a new reference image")
    trigger_new_reference_image_date = models.DateTimeField('date created', default=timezone.now)
    reference_image_version = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(9999)])
    history = HistoricalRecords()

    def __str__(self):
        return f'{self.camera_name} / #{self.camera_number}'

    def get_slug_camera_name(self):
        return reverse('images', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        self.slug = slugify(self.camera_name)
        return super().save(*args, **kwargs)


class ReferenceImage(models.Model):
    def get_image_filename(instance, filename):
        h = now().strftime('%H')
        # print("url is", instance.url)
        return f'base_images/{instance.url}/{h}-{filename}'

    def get_hour(self):
        # print("reference hour is", now().strftime('%H'))
        return now().strftime('%H')

    url = models.ForeignKey(Camera, on_delete=models.CASCADE,
                            verbose_name="Camera Name and Number", help_text="points to camera id")
    image = models.ImageField(max_length=300, upload_to=get_image_filename, verbose_name="Reference Image")
    hour = models.CharField(max_length=2, null=False, blank=False, default=get_hour)
    light_level = models.DecimalField(max_digits=5, null=False, blank=False, decimal_places=2, default=0)
    focus_value = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    # matching_threshold = models.DecimalField(max_digits=3, decimal_places=2,
    #                                          validators=[MaxValueValidator(1), MinValueValidator(0)],
    #                                          default=0)
    # focus_value_threshold = models.DecimalField(max_digits=6, decimal_places=2,
    #                                             validators=[MaxValueValidator(9999), MinValueValidator(0)],
    #                                             default=0)
    # light_level_threshold = models.DecimalField(max_digits=5, decimal_places=2,
    #                                             validators=[MaxValueValidator(255), MinValueValidator(0)],
    #                                             default=0)
    creation_date = models.DateTimeField('date created', default=timezone.now)
    version = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(9999)])
    # history = HistoricalRecords()

    def __str__(self):
        return f'{self.image}'


class LogImage(models.Model):
    url = models.ForeignKey('main_menu.Camera', on_delete=models.CASCADE, verbose_name="Camera Name and Number")
    image = models.ImageField(upload_to='logs/%Y/%m/%d')
    matching_score = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    region_scores = models.JSONField(default=dict)
    current_matching_threshold = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    focus_value = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    current_focus_value = models.DecimalField(max_digits=7, null=True, blank=True, decimal_places=2, default=0)
    light_level = models.DecimalField(max_digits=5, null=True, blank=True, decimal_places=2, default=0)
    current_light_level = models.DecimalField(max_digits=5, null=False, blank=False, decimal_places=2, default=0)
    action = models.CharField(max_length=20, null=True)
    creation_date = models.DateTimeField('date created', default=timezone.now)
    user = models.CharField(choices=STATE_CHOICES, max_length=32, null=True, blank=True, default=None)
    run_number = models.PositiveIntegerField(null=False, blank=False, default=0)
    reference_image = models.ForeignKey('main_menu.ReferenceImage', on_delete=models.CASCADE,
                                        verbose_name="Reference Image", null=True, blank=True)

    # history = HistoricalRecords()

    def __str__(self):
        return f'{self.image}'


class Licensing(models.Model):
    start_date = models.DateField('license start date', null=False, blank=False, default=timezone.now)
    end_date = models.DateField('license end date', null=False, blank=False, default=timezone.now)
    transaction_limit = models.IntegerField(null=False, blank=False,
                                            validators=[
                                                MaxValueValidator(99999999),
                                                MinValueValidator(1)
                                                       ]
                                            )
    transaction_count = models.IntegerField(null=False, blank=False, default=0)
    license_key = models.CharField(max_length=256, null=False, blank=False, default="None")
    license_owner = models.CharField(max_length=256, null=False, blank=False, default="None")
    site_name = models.CharField(max_length=256, null=False, blank=False, default="None")
    run_schedule = models.PositiveIntegerField(null=False, blank=False, default=1,
                                               validators=[
                                                   MaxValueValidator(168),
                                                   MinValueValidator(1)]
                                               )
    # TODO run_schedule seems like its not being used - check and remove

class EngineState(models.Model):
    state = models.CharField(choices=STATE_CHOICES, max_length=32)
    number_of_cameras_in_run = models.PositiveIntegerField(null=False, blank=False, default=0)
    transaction_rate = models.PositiveIntegerField(null=False, blank=False, default=0)
    state_timestamp = models.DateTimeField('run completion time', null=False, blank=False, default=timezone.now)
    number_failed_images = models.PositiveIntegerField(null=False, blank=False, default=0)
    number_pass_images = models.PositiveIntegerField(null=False, blank=False, default=0)
    number_others = models.PositiveIntegerField(null=False, blank=False, default=0)
    user = models.CharField(choices=STATE_CHOICES, max_length=32, null=True, blank=True, default=None)

    @property
    def progress(self):
        # Perform your calculation here
        if self.number_of_cameras_in_run != 0:
            return ((self.number_pass_images + self.number_failed_images + self.number_others)
                    / self.number_of_cameras_in_run) * 100
        else:
            return 0  # Handle division by zero or other cases