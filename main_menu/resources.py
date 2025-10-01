import os
from tokenize import group

from import_export import resources
from django.db import IntegrityError
from import_export.admin import ImportExportModelAdmin
from django.conf import settings
import logging

from .models import Camera, ReferenceImage, Group
from django.core.validators import ValidationError
from django.core.exceptions import ObjectDoesNotExist


__version__ = 2.1


class GroupResource(resources.ModelResource):

    class Meta:
        model = Group
        skip_unchanged = True
        # exclude = ('id',)
        fields = ('group_name')
        import_id_fields = ('group_name')
        report_skipped = True
        raise_errors = True


class CameraResource(resources.ModelResource):
    def before_import_row(self, row, row_number=None, **kwargs):
        """Preserve existing values for specific fields if they are missing in the CSV."""
        try:
            # instance = Camera.objects.get(psn_recorded_port=row["psn_recorded_port"])  # Get the existing camera object
            instance = Camera.objects.get(camera_number=row["camera_number"])  # Get the existing camera object

            # Preserve image_regions if blank
            if "image_regions" in row and (
                    not row["image_regions"] or row["image_regions"].strip() in ["", "[]", "None"]):
                row["image_regions"] = instance.image_regions  # Keep existing value

            # Preserve DecimalFields if blank
            for field in ["matching_threshold", "focus_value_threshold", "light_level_threshold"]:
                if field in row and (not row[field] or str(row[field]).strip() in ["", "None"]):
                    row[field] = instance.__dict__[field]  # Keep existing value
            if "camera_name" in row and (not row["camera_name"] or row["camera_name"].strip() in ["", "None"]):
                row["camera_name"] = instance.camera_name  # Keep existing value

                # Preserve CAMERA_LOCATION if blank
            if "camera_location" in row and (
                    not row["camera_location"] or row["camera_location"].strip() in ["", "None"]):
                row["camera_location"] = instance.camera_location  # Keep existing value

                # Preserve PSN_IP_ADDRESS if blank
            if "psn_ip_address" in row and (not row["psn_ip_address"] or row["psn_ip_address"].strip() in ["", "None"]):
                row["psn_ip_address"] = instance.psn_ip_address  # Keep existing value

            if "psn_user_name" in row and (not row["psn_user_name"] or row["psn_user_name"].strip() in ["", "None"]):
                row["psn_user_name"] = instance.psn_user_name  # Keep existing value

            if "psn_password" in row and (not row["psn_password"] or row["psn_password"].strip() in ["", "None"]):
                row["psn_password"] = instance.psn_password  # Keep existing value

        except ObjectDoesNotExist:
            pass  # If new, no existing data to preserve

    class Meta:
        model = Camera
        skip_unchanged = True
        # exclude = ('id',)
        fields = ('url', 'multicast_address', 'multicast_port', 'camera_username',
                  'camera_password', 'camera_number', 'camera_name',
                  'camera_location', 'image_regions', 'matching_threshold',
                  'focus_value_threshold', 'light_level_threshold', 'reference_image_version', 'snooze',
                  'psn_ip_address', 'psn_name', 'psn_recorded_port', 'psn_user_name', 'psn_password', 'freeze_check',
                  'group_name')
        # import_id_fields = ('url', 'multicast_address', 'multicast_port')
        # import_id_fields = ('psn_recorded_port',)
        import_id_fields = ('camera_number',)
        report_skipped = True
        raise_errors = True
        update_existing = True

    def import_row(self, row, instance_loader, **kwargs):
        try:
            return super().import_row(row, instance_loader, **kwargs)
        except IntegrityError as e:
            # Log the error or add it to a list of problematic rows
            # You can access the row data using 'row' and the error message using 'str(e)'
            error_message = str(e)
            problematic_row = row  # The problematic data
            logging.error(f"Error with row {problematic_row} - {error_message}")
            raise ValidationError(error_message)

    def save_instance(self, instance, is_validcreated=True, using_transactions=True, dry_run=False):
        try:
            super(CameraResource, self).save_instance(instance, using_transactions, dry_run)
        except IntegrityError as e:
            error_message = str(e)
            logging.error(f"Error saving import for {instance} error is {e}")
            raise ValidationError(error_message)



    def after_save_instance(self, instance, using_transactions, dry_run):
        # the model instance will have been saved at this point, and will have a pk
        if not dry_run:
            if not os.path.isdir(f'{settings.MEDIA_ROOT}/base_images/{instance.pk}'):
                # print("directory doesnt exists")
                os.mkdir(f'{settings.MEDIA_ROOT}/base_images/{instance.pk}')



class ReferenceImageResource(resources.ModelResource):

    class Meta:
        model = ReferenceImage
        # exclude = ('id',)
        fields = ('image', 'hour')

#
# class CameraResult(ImportExportModelAdmin):
#     resource_class = CameraResource
#     import_id_fields = ('url', 'camera_number', 'camera_name', '
#     camera_location', 'image_regions', 'matching_threshold')
