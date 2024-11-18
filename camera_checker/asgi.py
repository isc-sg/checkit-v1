"""
ASGI config for camera_checker project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.umask(0o002)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'camera_checker.settings')

application = get_asgi_application()
