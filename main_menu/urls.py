from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from rest_framework import routers
from django.views.generic import TemplateView
# from rest_framework.schemas import get_schema_view
from django.views.decorators.csrf import csrf_exempt
# from rest_framework.schemas.openapi import AutoSchema
from django.urls import re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi


from main_menu import views
from .views import ActiveTasksView, CheckCamerasView, CheckSoftwareVersionsView


__version__ = 2.1

schema_view = get_schema_view(
   openapi.Info(
      title="Checkit API",
      default_version='v2',
      description="Rest framework to access camera,logs, reference images, scheduler",
      
      contact=openapi.Contact(email="sam.corbo@isc.sg"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

router = routers.DefaultRouter()
# router.register(r'users', views.UserViewSet)
# router.register(r'groups', views.GroupViewSet)
router.register(r'^/cameras_api', views.CameraViewSet)
# router.register(r'^/logs_api', views.LogImageViewSet)
# router.register(r'^/check_camera', views.CheckCamerasView, basename="check_camera")
# router.register(r'^/reference_image_api', views.ReferenceImageListCreateAPIView.as_view, 'reference-images-list')
# router.register(r'^/reference_image_api/<int:pk>/', views.ReferenceImagesDetailAPIView.as_view  , 'reference-images-detail')
# router.register(r'^/snooze_api', views.ReferenceImageViewSet)
# router.register(r'index', views.index)


urlpatterns = [
    path("api/reference_image_api/", views.ReferenceImageListCreateAPIView.as_view(),  name='reference-images-list-create'),
    path("api/check_camera/", views.CheckCamerasView.as_view(),  name='check_camera'),
    path("api/logs_api/", views.LogImageViewSet.as_view(),  name='log_view'),
    path('api/reference_image_api/<int:pk>/', views.ReferenceImagesDetailAPIView.as_view(), name='reference-images-detail'),
    path('api', include(router.urls)),
    path('', views.index, name='home'),
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/scheduler/active-tasks/', ActiveTasksView.as_view(), name='active_tasks'),
    path('api/software_versions/', CheckSoftwareVersionsView.as_view(), name='software_versions'),


    # path('api/schema', get_schema_view(
    #       title="Checkit",
    #       description="Checkit API",
    #       version="1.1.0"
    #   ), name='checkit-schema'),
    path('import/', views.simple_upload, name="import"),
    path('reference_image/', csrf_exempt(views.reference_image_api)),
    # path('snooze/', csrf_exempt(views.snooze_api)),
    # path('api/snooze_api/', SnoozeCamera.as_view(), name='snooze-api'),
    path("status/", views.index, name='status'),
    path("scheduler/", views.scheduler, name='scheduler'),
    path('cameras/', views.CameraView.as_view(), name='cameras'),
    path('cameras_mass_admin/', views.CameraSelectView.as_view(), name='cameras_mass_admin'),
    path("mass_update/", views.mass_update, name='mass update'),
    path('logs/', views.LogView.as_view(), name="logs"),
    path("state/", views.EngineStateView.as_view(), name='state'),
    path('license/', views.licensing, name='licensing'),
    path("display_regions/", views.display_regions, name='test'),
    path("export/", views.export_logs_to_csv, name='export csv logs'),
    path("images/", views.compare_images, name="images"),
    path('regions/', views.input_camera_for_regions, name='regions'),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('get_engine_status/', views.get_engine_status, name='get_progress'),
    path('progress_meter/', views.progress_meter, name='progress_meter'),
    path('missing_reference_images/', views.cameras_with_missing_reference_images, name='missing_ref'),
    path('log_summary/', views.action_per_hour_report, name='log_summary'),
              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += staticfiles_urlpatterns()
urlpatterns += [
    path('accounts/', include('django.contrib.auth.urls')),
]
