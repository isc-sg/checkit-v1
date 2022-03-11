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


class Camera(models.Model):
    url = models.CharField(max_length=300, unique=True, verbose_name="Camera URL")
    # image = models.ImageField(upload_to='base_images/')
    camera_number = models.IntegerField(null=False, blank=False, unique=True,
                                        validators=[
                                          MaxValueValidator(100000),

                                          MinValueValidator(1)])
    camera_name = models.CharField(max_length=100, null=False, blank=False, unique=True)
    slug = models.SlugField(max_length=100, null=True, blank=False, unique=True, verbose_name="URL friendly name")
    camera_location = models.CharField(max_length=100)
    image_regions = models.CharField(max_length=300, default="[]")
    matching_threshold = models.DecimalField(max_digits=3, decimal_places=2, default=0.5)
    creation_date = models.DateTimeField('date created', default=timezone.now)
    last_check_date = models.DateTimeField('date checked', default=timezone.now)
    history = HistoricalRecords()

    def __str__(self):
        return f'{self.camera_name} / #{self.camera_number}'

    def get_slug_camera_name(self):
        return reverse('images', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        self.slug = slugify(self.camera_name)
        return super().save(*args, **kwargs)


class ReferenceImage(models.Model):
    def get_image_filename(self, filename):
        h = now().strftime('%H')
        return f'base_images/{self.url.id}/{h}-{filename}'

    def get_hour():
        return now().strftime('%H')

    url = models.ForeignKey(Camera, on_delete=models.CASCADE, verbose_name="Camera Name and Number")
    image = models.ImageField(max_length=300, upload_to=get_image_filename, verbose_name="Reference Image")
    hour = models.CharField(max_length=2, null=False, blank=False, default=get_hour)
    history = HistoricalRecords()

    def __str__(self):
        return f'{self.url}/{self.image}'


class LogImage(models.Model):
    url = models.ForeignKey('main_menu.Camera', on_delete=models.CASCADE, verbose_name="Camera Name and Number")
    image = models.ImageField(upload_to='logs/%Y/%m/%d')
    matching_score = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    region_scores = models.JSONField(default=dict)
    current_matching_threshold = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    focus_value = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    action = models.CharField(max_length=20, null=True)
    creation_date = models.DateTimeField('date created', default=timezone.now)
    history = HistoricalRecords()

    def __str__(self):
        return f'{self.url}/{self.creation_date}'


class Licensing(models.Model):
    start_date = models.DateField('license start date', null=False, blank=False, default=timezone.now)
    end_date = models.DateField('license end date', null=False, blank=False, default=timezone.now)
    transaction_limit = models.IntegerField(null=False, blank=False,
                                            validators=[
                                                MaxValueValidator(9999999),
                                                MinValueValidator(1)
                                                       ]
                                            )
    transaction_count = models.PositiveIntegerField(null=False, blank=False, default=0)
    license_key = models.CharField(max_length=256, null=False, blank=False, default="None")
    license_owner = models.CharField(max_length=256, null=False, blank=False, default="None")
    site_name = models.CharField(max_length=256, null=False, blank=False, default="None")
    run_schedule = models.PositiveIntegerField(null=False, blank=False, default=1,
                                               validators=[
                                                   MaxValueValidator(168),
                                                   MinValueValidator(1)]
                                               )


class EngineState(models.Model):
    state = models.CharField(choices=STATE_CHOICES, max_length=32)
    engine_process_id = models.PositiveIntegerField(null=False, blank=False, default=0)
    transaction_rate = models.PositiveIntegerField(null=False, blank=False, default=0)
    state_timestamp = models.DateTimeField('run completion time', null=False, blank=False, default=timezone.now)
    number_failed_images = models.PositiveIntegerField(null=False, blank=False, default=0)
