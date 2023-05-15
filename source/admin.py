import logging

from django.contrib import admin
from django.conf import settings
import shutil
from django.utils.safestring import mark_safe
from django.template.defaultfilters import slugify
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from django.contrib import admin
from django.contrib.admin.models import LogEntry, DELETION
from django.utils.html import escape
from django.urls import reverse
from django.utils.safestring import mark_safe
from rangefilter.filters import DateRangeFilter
from django_admin_listfilter_dropdown.filters import DropdownFilter, RelatedDropdownFilter, ChoiceDropdownFilter


import os

# Register your models here.
# from .models import Camera, ReferenceImage, LogImage
from .models import Camera, ReferenceImage, LogImage, DaysOfWeek, HoursInDay
from .resources import CameraResource, ReferenceImageResource

admin.site.site_title = "CheckIT"
admin.site.site_header = "CheckIT"
admin.site.index_title = "CheckIT Admin"


class CameraAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    massadmin_exclude = ['url', 'camera_number', 'camera_name', 'multicast_address', 'creation_date', "last_check_date",
                         'slug']
    filter_horizontal = ('scheduled_hours', 'scheduled_days')
    resource_class = CameraResource
    search_fields = ['url', 'camera_number', 'camera_name', 'camera_location']
    exclude = ('id',)
    list_display = ('camera_name', 'camera_number', 'url', 'multicast_address',
                    'camera_location', 'matching_threshold',)
    readonly_fields = ["creation_date", "last_check_date", 'image_regions']
    prepopulated_fields = {'slug': ('camera_name',)}
    list_filter = (('camera_location', DropdownFilter), ('scheduled_hours', RelatedDropdownFilter),
                   ('scheduled_days', RelatedDropdownFilter))

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


class ReferenceAdmin(SimpleHistoryAdmin):
    # model = ReferenceImage
    resource_class = ReferenceImageResource
    search_fields = ['url__camera_name', 'url__camera_number', 'image']
    exclude = ('id',)
    list_display = ['url', 'hour', 'reference_image', 'get_location']
    readonly_fields = ['url', 'hour', 'get_regions', 'reference_image', 'light_level']
    list_filter = (('hour', DropdownFilter), ('url__camera_location', DropdownFilter))

    def has_add_permission(self, request, obj=None):
        return False

    def get_regions(self, obj):
        return obj.url.image_regions
    get_regions.short_description = "Regions"

    def reference_image(self, obj):
        return mark_safe('<img src="{url}" width="{width}" height={height} />'.format(
            url=obj.image.url,
            width=(obj.image.width/4),
            height=(obj.image.height/4),
                                                                                     )
                        )

    def get_location(self, obj):
        return obj.url.camera_location
    get_location.short_description = "Location"


class LogImageAdmin(SimpleHistoryAdmin):
    resource_class = LogImage
    search_fields = ['url__camera_name', 'image', 'action', 'creation_date', 'url__camera_location']
    list_display = ['url', 'creation_date', 'action', 'get_location', ]
    exclude = ('id', 'region_scores')
    readonly_fields = ('url', 'image', 'matching_score', 'current_matching_threshold', 'focus_value', 'action',
                       'creation_date', 'log_image')
    list_filter = (('creation_date', DateRangeFilter), ('url__camera_location', DropdownFilter))

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
