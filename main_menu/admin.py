import logging
import os
import shutil

from django.contrib import admin
from django.conf import settings
from django.utils.safestring import mark_safe
from django.template.defaultfilters import slugify
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.contrib.admin.models import LogEntry, DELETION
from django.utils import timezone
from django.utils.html import escape
from django.urls import reverse
from django.utils.safestring import mark_safe
from rangefilter.filters import DateRangeFilter, DateTimeRangeFilter
from django_admin_listfilter_dropdown.filters import DropdownFilter, RelatedDropdownFilter, ChoiceDropdownFilter
from django.views.decorators.cache import cache_control, add_never_cache_headers
from django.utils.decorators import method_decorator
from django_celery_beat.apps import BeatConfig
from .models import Camera, ReferenceImage, LogImage, DaysOfWeek, HoursInDay
from .resources import CameraResource, ReferenceImageResource
BeatConfig.verbose_name = "Checkit Clocks"

# Register your models here.
# from .models import Camera, ReferenceImage, LogImage


admin.site.site_title = "CheckIT"
admin.site.site_header = "CheckIT"
admin.site.index_title = "CheckIT Admin"


class DisableClientSideCachingMiddleware(object):
    def process_response(self, request, response):
        add_never_cache_headers(response)
        return response


def new_reference_image(modeladmin, request, queryset):
    # Code to run your custom function
    # For example, call your function from views.py
    # selected_camera_ids = queryset.values_list('pk', flat=True)
    # from .views import trigger_new_reference_image
    # trigger_new_reference_image(selected_camera_ids)
    selected_camera_ids = queryset
    for camera in selected_camera_ids:
        camera.trigger_new_reference_image = True
        camera.trigger_new_reference_image_date = timezone.now()
        camera.save()


new_reference_image.short_description = "Trigger New Reference Image"


class CameraAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):

    massadmin_exclude = ['url', 'camera_number', 'camera_name', 'multicast_address', 'creation_date', "last_check_date",
                         'slug']
    filter_horizontal = ('scheduled_hours', 'scheduled_days')
    resource_class = CameraResource
    search_fields = ['url', 'camera_number', 'camera_name', 'camera_location', 'id']
    list_display = ('camera_name', 'camera_number', 'url', 'multicast_address', 'multicast_port',
                    'camera_location', 'matching_threshold', 'unique_camera_id', 'check_reference_image')
    readonly_fields = ["unique_camera_id", "creation_date", "last_check_date", 'image_regions']
    prepopulated_fields = {'slug': ('camera_name',)}
    list_filter = (('camera_location', DropdownFilter), ('scheduled_hours', RelatedDropdownFilter),
                   ('scheduled_days', RelatedDropdownFilter))
    history_list_display = ["matching_threshold", "focus_value_threshold", "light_level_threshold"]
    actions = [new_reference_image]


    def unique_camera_id(self, obj):
        return obj.id

    def save_model(self, request, obj, form, change):
        obj.save()

        if not change:
            # only set owner when object is first created
            # print("not changed", obj.id)
            # print(f'{settings.MEDIA_ROOT}/base_images/{obj.id}')
            if not os.path.isdir(f'{settings.MEDIA_ROOT}/base_images/{obj.id}'):
                # print("directory doesnt exists")
                os.mkdir(f'{settings.MEDIA_ROOT}/base_images/{obj.id}')
        # else:
        #     print("changed", obj.id)
        #     print(form.data['camera_name'])
        #     print(slugify(form.data['camera_name']))
        #     new_name = slugify(form.data['camera_name'])
        #     shutil.move(f'{settings.MEDIA_ROOT}/base_images/{obj.slug}',
        #                 f'{settings.MEDIA_ROOT}/base_images/{new_name}')
        # print("New id is", obj.id)

    def check_reference_image(self, obj):
        r = ReferenceImage.objects.filter(url=obj.id)
        return r.exists()

    check_reference_image.short_description = 'Has Ref'
    check_reference_image.boolean = True  # Display as a boolean field

    # Custom method for filtering

    def delete_model(self, request, obj):
        # print(f'{settings.MEDIA_ROOT}/base_images/{obj.id}')
        try:
            shutil.rmtree(f'{settings.MEDIA_ROOT}/base_images/{obj.id}')
        except OSError:
            logging.error(f"Unable to delete {settings.MEDIA_ROOT}/base_images/{obj.id}")
        obj.delete()

    def delete_queryset(self, request, queryset):
        for camera in queryset:
            # print(camera.id)
            try:
                shutil.rmtree(f'{settings.MEDIA_ROOT}/base_images/{camera.id}')
            except OSError:
                logging.error(f"Unable to delete {settings.MEDIA_ROOT}/base_images/{camera.id}")
        queryset.delete()


class ReferenceAdmin(ModelAdmin):
    # model = ReferenceImage

    resource_class = ReferenceImageResource
    search_fields = ['url__camera_name', 'url__camera_number', 'image']
    # exclude = ('id',)
    list_display = ['url', 'hour', 'version', 'reference_image', 'get_location']
    readonly_fields = ['url', 'hour', 'get_regions', 'reference_image',
                       'light_level', 'focus_value', 'creation_date', 'version']
    list_filter = (('hour', DropdownFilter), ('url__camera_location', DropdownFilter), ('version', DropdownFilter))
    fields = ['url', 'hour', 'get_regions', 'reference_image', 'light_level', 'focus_value', 'creation_date', 'version']
    exclude = ['trigger_new_version']

    def has_add_permission(self, request, obj=None):
        return False

    def get_regions(self, obj):
        return obj.url.image_regions
    get_regions.short_description = "Regions"

    def reference_image(self, obj):
        scaling_factor = 4
        if obj.image.width <= 720:
            scaling_factor = 2
        if obj.image.width > 1920:
            scaling_factor = (obj.image.width / 1920) * 4
        return mark_safe('<img src="{url}" width="{width}" height={height} />'.format(
            url=obj.image.url,
            width=(obj.image.width/scaling_factor),
            height=(obj.image.height/scaling_factor),
                                                                                     )
                        )

    def get_location(self, obj):
        return obj.url.camera_location
    get_location.short_description = "Location"

    # def delete_model(self, request, obj):
    #     logs = LogImage.objects.filter(reference_image_id=obj.id)
    #     try:
    #         logs.delete()
    #     except:
    #         pass
    #     obj.delete()
    #
    # def delete_queryset(self, request, queryset):
    #     for ref in queryset:
    #         logs = LogImage.objects.filter(reference_image_id=ref.id)
    #         try:
    #             logs.delete()
    #         except:
    #             pass
    #     queryset.delete()


class LogImageAdmin(ModelAdmin):
    resource_class = LogImage
    search_fields = ['url__camera_name', 'image', 'action', 'creation_date', 'url__camera_location']
    list_display = ['url', 'creation_date', 'action', 'get_location', ]
    exclude = ('id', 'region_scores')
    readonly_fields = ('url', 'image', 'matching_score', 'current_matching_threshold', 'focus_value', 'action',
                       'creation_date', 'log_image', 'user', 'run_number')
    list_filter = (('creation_date', DateTimeRangeFilter), ('action', DropdownFilter), ('url__camera_location', DropdownFilter))

    def log_image(self, obj):
        return mark_safe('<img src="{url}" width="{width}" height={height} />'.format(
            url=obj.image.url,
            width=(obj.image.width/2),
            height=(obj.image.height/2),
                                                                                     )
                        )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['readonly'] = True
        return super(LogImageAdmin, self).change_view(request, object_id, extra_context=extra_context)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    # def has_delete_permission(self, request, obj=None):
    #     return False

    def get_location(self, obj):
        return obj.url.camera_location
    get_location.short_description = "Location"



@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    date_hierarchy = 'action_time'

    list_filter = [
        'user',
        'content_type',
        'action_flag'
    ]

    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'action_time',
        'user',
        'content_type',
        'object_link',
        'action_flag',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def object_link(self, obj):
        if obj.action_flag == DELETION:
            link = escape(obj.object_repr)
        else:
            ct = obj.content_type
            link = '<a href="%s">%s</a>' % (
                reverse('admin:%s_%s_change' % (ct.app_label, ct.model), args=[obj.object_id]),
                escape(obj.object_repr),
            )
        return mark_safe(link)
    object_link.admin_order_field = "object_repr"
    object_link.short_description = "record"


admin.site.register(Camera, CameraAdmin)
admin.site.register(ReferenceImage, ReferenceAdmin)
admin.site.register(LogImage, LogImageAdmin)
