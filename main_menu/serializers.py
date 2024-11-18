from django.contrib.auth.models import User, Group
from .models import Camera, LogImage, ReferenceImage
from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta


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
        fields = ['id', 'url', 'multicast_address', 'multicast_port', 'camera_username', 'camera_password',
                  'camera_number', 'camera_name', 'camera_location',
                  'matching_threshold', 'focus_value_threshold', 'light_level_threshold',
                  'scheduled_hours', 'scheduled_days', 'snooze', 'trigger_new_reference_image', 'psn_ip_address',
                  'psn_name', 'psn_recorded_port', 'psn_user_name', 'psn_password', 'freeze_check']
        # extra_kwargs = {
        #     'url': {'lookup_field': 'hoursinday'}
        # }

    def create(self, validated_data):
        trigger_new_reference_image = validated_data.get('trigger_new_reference_image', False)

        instance = super().create(validated_data)

        if trigger_new_reference_image:
            instance.trigger_new_reference_image_date = timezone.now() + timedelta(hours=24)
            instance.save()

        return instance

    def update(self, instance, validated_data):
        trigger_new_reference_image = validated_data.get('trigger_new_reference_image',
                                                         instance.trigger_new_reference_image)

        instance = super().update(instance, validated_data)

        if trigger_new_reference_image:
            instance.trigger_new_reference_image_date = timezone.now() + timedelta(hours=24)
            instance.save()

        return instance


class LogImageSerializer(serializers.ModelSerializer):
    # camera = CameraSerializer(source='url', read_only=True)

    class Meta:
        model = LogImage
        fields = ['url', 'image', 'matching_score', 'region_scores', 'current_matching_threshold',
                  'focus_value', 'current_focus_value', 'light_level',
                  'current_light_level', 'action', 'creation_date',
                  'user', 'run_number', 'reference_image']


class ReferenceImageSerializer(serializers.ModelSerializer):
    # camera = CameraSerializer(source='url', read_only=True)

    class Meta:
        model = ReferenceImage
        fields = ['id', 'url', 'image', 'hour', 'light_level',
                  'focus_value', 'creation_date',
                  'version']


class SnoozeCameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = ['snooze', 'camera_number',]
