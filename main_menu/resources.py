from import_export import resources
from django.db import IntegrityError
from import_export.admin import ImportExportModelAdmin

from .models import Camera, ReferenceImage


class CameraResource(resources.ModelResource):

    class Meta:
        model = Camera
        skip_unchanged = True
        exclude = ('id',)
        fields = ('url', 'camera_number', 'camera_name',
                  'camera_location', 'image_regions', 'matching_threshold',)
        import_id_fields = ('url', 'camera_number', 'camera_name',
                            'camera_location', 'image_regions', 'matching_threshold')

    def save_instance(self, instance, using_transactions=True, dry_run=False):
        try:
            super(CameraResource, self).save_instance(instance, using_transactions, dry_run)
        except IntegrityError:
            pass


class ReferenceImageResource(resources.ModelResource):

    class Meta:
        model = ReferenceImage
        exclude = ('id',)
        fields = ('image', 'hour')

#
# class CameraResult(ImportExportModelAdmin):
#     resource_class = CameraResource
#     import_id_fields = ('url', 'camera_number', 'camera_name', 'camera_location', 'image_regions', 'matching_threshold')
