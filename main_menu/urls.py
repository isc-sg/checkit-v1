from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from rest_framework import routers
from django.views.generic import TemplateView
from rest_framework.schemas import get_schema_view

from main_menu import views

router = routers.DefaultRouter()
# router.register(r'users', views.UserViewSet)
# router.register(r'groups', views.GroupViewSet)
router.register(r'/cameras_api', views.CameraViewSet)
# router.register(r'index', views.index)

urlpatterns = [
    path('api', include(router.urls)),
    path('', views.index, name='home'),

    path('openapi', get_schema_view(
          title="Checkit",
          description="Checkit API",
          version="1.0.0"
      ), name='openapi-schema'),
    # path('swagger-ui/', TemplateView.as_view(
    #     template_name='swagger-ui.html',
    #     extra_context={'schema_url': 'openapi-schema'}
    # ), name='swagger-ui'),
    path('import/', views.simple_upload, name="import"),
    path('camera_api/<int:camera_number>/', views.CameraDetail),
    path("status/", views.index, name='status'),
    path("scheduler/", views.scheduler, name='scheduler'),
    path('cameras/', views.CameraView.as_view(), name='cameras'),
    path('logs/', views.LogView.as_view(), name="logs"),
    path("state/", views.EngineStateView.as_view(), name='state'),
    path('license/', views.licensing, name='licensing'),
    path("date/", views.get_date, name='date'),
    path("display_regions/", views.display_regions, name='test'),
    path("export/", views.export_logs_to_csv, name='export csv logs'),
    path("images/", views.compare_images, name="images"),
    path('regions/', views.input_camera_for_regions, name='regions'),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework'))

              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += staticfiles_urlpatterns()
urlpatterns += [
    path('accounts/', include('django.contrib.auth.urls')),
]
