from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

from . import views


urlpatterns = [
    path('', views.index, name='home'),
    path('import/', views.simple_upload, name="import"),
    path("status/", views.index, name='status'),
    path("scheduler/", views.scheduler, name='scheduler'),
    path('cameras/', views.CameraView.as_view()),
    path('logs/', views.LogView.as_view(), name="logs"),
    path("state/", views.EngineStateView.as_view()),
    path('license/', views.licensing, name='licensing'),
    path("date/", views.get_date, name='date'),
    path("export/", views.export_logs_to_csv, name='export csv logs'),
    path("images/", views.compare_images, name="images"),
    path('show_ref/<int:camera_number>/', views.display_image_in_page_from_memory, name='ref_image'),
    path('regions/', views.display_image_grid_regions, name='regions'),

              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += staticfiles_urlpatterns()
urlpatterns += [
    path('accounts/', include('django.contrib.auth.urls')),
]
