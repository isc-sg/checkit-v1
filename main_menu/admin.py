from django.contrib import admin
from django.utils.safestring import mark_safe
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin


# Register your models here.
from .models import Camera, ReferenceImage, LogImage
from .resources import CameraResource, ReferenceImageResource


class CameraAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    resource_class = CameraResource
    search_fields = ['url', 'camera_number', 'camera_name', 'camera_location']
    exclude = ('id',)
    list_display = ('camera_name', 'camera_number', 'url',
                    'camera_location', 'matching_threshold',)
    readonly_fields = ["creation_date", "last_check_date",]
    prepopulated_fields = {'slug': ('camera_name',)}
    list_filter = ['camera_location']


class ReferenceAdmin(admin.ModelAdmin):
    # model = ReferenceImage
    resource_class = ReferenceImageResource
    search_fields = ['url__camera_name', 'url__camera_number', 'image']
    exclude = ('id',)
    list_display = ['url', 'hour', 'reference_image', 'get_location']
    readonly_fields = ['hour', 'get_regions', 'reference_image', ]
    list_filter = ['hour', 'url__camera_location']

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


class LogImageAdmin(admin.ModelAdmin):
    resource_class = LogImage
    search_fields = ['url__camera_name', 'image', 'action', 'creation_date']
    list_display = ['url', 'creation_date', 'get_location']
    exclude = ('id', 'region_scores')
    readonly_fields = ('url', 'image', 'matching_score', 'current_matching_threshold', 'focus_value', 'action',
                       'creation_date', 'log_image')
    list_filter = ['creation_date', 'url__camera_location']

    def log_image(self, obj):
        return mark_safe('<img src="{url}" width="{width}" height={height} />'.format(
            url=obj.image.url,
            width=(obj.image.width/2),
            height=(obj.image.height/2),
                                                                                     )
                        )

    def get_location(self, obj):
        return obj.url.camera_location
    get_location.short_description = "Location"

admin.site.register(Camera, CameraAdmin)
admin.site.register(ReferenceImage, ReferenceAdmin)
admin.site.register(LogImage, LogImageAdmin)
