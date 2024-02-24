from django.contrib.auth.models import User, Group
from .models import Camera
from rest_framework import serializers

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
        fields = ['url', 'multicast_address', 'multicast_port', 'camera_username', 'camera_password',
                  'camera_number', 'camera_name', 'camera_location',
                  'matching_threshold', 'focus_value_threshold', 'light_level_threshold',
                  'scheduled_hours', 'scheduled_days', 'snooze']
        # extra_kwargs = {
        #     'url': {'lookup_field': 'hoursinday'}
        # }