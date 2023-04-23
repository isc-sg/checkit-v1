import os
from import_export import resources
from django.db import IntegrityError
from import_export.admin import ImportExportModelAdmin
from django.conf import settings

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

<<<<<<< HEAD
    def save_instance(self, instance, using_transactions=True, dry_run=False):
=======
    def save_instance(self, instance, is_created=True, using_transactions=True, dry_run=False):
>>>>>>> added heap of changes that were not pushed up since september 2022.  Some known - fixed bug with pdf creation where log or reference image were deleted.  Added code to push message to synergy. Current version has Synergy skin
        try:
            super(CameraResource, self).save_instance(instance, using_transactions, dry_run)
        except IntegrityError:
            pass

    def after_save_instance(self, instance, using_transactions, dry_run):
        # the model instance will have been saved at this point, and will have a pk
        if not dry_run:
            if not os.path.isdir(f'{settings.MEDIA_ROOT}/base_images/{instance.pk}'):
                # print("directory doesnt exists")
                os.mkdir(f'{settings.MEDIA_ROOT}/base_images/{instance.pk}')


class ReferenceImageResource(resources.ModelResource):

    class Meta:
        model = ReferenceImage
        exclude = ('id',)
        fields = ('image', 'hour')

#
# class CameraResult(ImportExportModelAdmin):
#     resource_class = CameraResource
#     import_id_fields = ('url', 'camera_number', 'camera_name', 'camera_location', 'image_regions', 'matching_threshold')
