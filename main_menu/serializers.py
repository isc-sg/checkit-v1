from django.contrib.auth.models import User, Group
from .models import Camera, LogImage, ReferenceImage
from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta


__version__ = 2.1

#
# class UserSerializer(serializers.HyperlinkedModelSerializer):
#     class Meta:
#         model = User
#         fields = ['url', 'username', 'email', 'groups']
#
#
# class GroupSerializer(serializers.HyperlinkedModelSerializer):
#     class Meta:
#         model = Group
#         fields = ['url', 'name']


class CameraSerializer(serializers.ModelSerializer):
    # hoursinday = serializers.HyperlinkedRelatedField(
    #             view_name='hoursinday-detail',
    #             lookup_field='HoursInDay',
    #             many=True,
    #             read_only=True)
    # daysofweek = serializers.HyperlinkedRelatedField(
    #             view_name='daysofweek-detail',
    #             lookup_field='DaysOfWeek',
    #             many=True,
    #             read_only=True)

    class Meta:
        model = Camera
        fields = [
            'id', 'url', 'multicast_address', 'multicast_port', 'camera_username', 'camera_password',
            'camera_number', 'camera_name', 'camera_location',
            'matching_threshold', 'focus_value_threshold', 'light_level_threshold',
            'scheduled_hours', 'scheduled_days', 'snooze',
            'trigger_new_reference_image', 'trigger_copy_to_all',
            'psn_ip_address', 'psn_name', 'psn_recorded_port', 'psn_user_name', 'psn_password', 'psn_api_method',
            'freeze_check', 'group_name',
            'disable', 'disable_reason', 'camera_disabled_date'
        ]
        # extra_kwargs = {
        #     'url': {'lookup_field': 'hoursinday'}
        # }

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)

        # Pull value from attrs if present; otherwise fall back to existing instance
        disable = attrs.get(
            'disable',
            getattr(instance, 'disable', False)
        )
        disable_reason = attrs.get(
            'disable_reason',
            getattr(instance, 'disable_reason', None)
        )
        trigger_new_reference_image = attrs.get(
            'trigger_new_reference_image',
            getattr(instance, 'trigger_new_reference_image', False)
        )
        trigger_copy_to_all = attrs.get(
            'trigger_copy_to_all',
            getattr(instance, 'trigger_copy_to_all', False)
        )

        # 1) If disabling -> reason required
        if disable and not (disable_reason and str(disable_reason).strip()):
            raise serializers.ValidationError({
                'disable_reason': 'Reason is required when disabling the camera.'
            })

        # 2) If enabling -> clear reason (date is read-only and cleared in update())
        if not disable:
            attrs['disable_reason'] = None

        # 3) If copy_to_all is True -> trigger must be True
        if trigger_copy_to_all and not trigger_new_reference_image:
            raise serializers.ValidationError({
                'trigger_copy_to_all': 'Requires trigger_new_reference_image to be True.'
            })

        return attrs

    def create(self, validated_data):
        # Auto-stamp disabled date if creating in disabled state
        if validated_data.get('disable') and not validated_data.get('camera_disabled_date'):
            validated_data['camera_disabled_date'] = timezone.now()

        trigger_new_reference_image = validated_data.get('trigger_new_reference_image', False)

        instance = super().create(validated_data)

        if trigger_new_reference_image:
            instance.trigger_new_reference_image_date = timezone.now() + timedelta(hours=24)
            instance.save()

        return instance

    def update(self, instance, validated_data):

        # Correcting the disable/enable transitions before save
        if 'disable' in validated_data:
            turning_off = not validated_data['disable']
            turning_on = validated_data['disable']

            if turning_on:
                # stamp if previously None
                if instance.camera_disabled_date is None:
                    instance.camera_disabled_date = timezone.now()
            if turning_off:
                # clear on re-enable
                instance.disable_reason = None
                instance.camera_disabled_date = None

        trigger_new_reference_image = validated_data.get('trigger_new_reference_image',
                                                         instance.trigger_new_reference_image)

        instance = super().update(instance, validated_data)

        if trigger_new_reference_image:
            instance.trigger_new_reference_image_date = timezone.now() + timedelta(hours=24)
            instance.save()

        return instance


class LogImageSerializer(serializers.ModelSerializer):
    camera = CameraSerializer(source='url.camera_number', read_only=True)

    class Meta:
        model = LogImage
        # fields = ['url', 'image', 'matching_score', 'region_scores', 'current_matching_threshold',
        #           'focus_value', 'current_focus_value', 'light_level',
        #           'current_light_level', 'action', 'creation_date',
        #           'user', 'run_number', 'reference_image']
        fields = '__all__'


class ReferenceImageSerializer(serializers.ModelSerializer):
    # camera = CameraSerializer(source='url', read_only=True)

    class Meta:
        model = ReferenceImage
        fields = ['id', 'url', 'image', 'hour', 'light_level',
                  'focus_value', 'creation_date',
                  'version']


# class SnoozeCameraSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Camera
#         fields = ['snooze', 'camera_number',]
