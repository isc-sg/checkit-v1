# django_celery/celery.py

from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.signals import setup_logging
import sys


sys.path.append(os.path.dirname(os.path.abspath("camera_checker")))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "camera_checker.settings")
app = Celery("camera_checker")
app.config_from_object("django.conf:settings", namespace="CELERY")


@setup_logging.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig  # noqa
    from django.conf import settings  # noqa

    dictConfig(settings.LOGGING)


@app.task(bind=True)
def hello_world(self):
    print('Hello world!')

app.autodiscover_tasks()

# app.conf.update(
#     task_track_started=True,
#     worker_send_task_events=True,
# )



