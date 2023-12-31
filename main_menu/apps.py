import logging
from logging.handlers import RotatingFileHandler
from django.apps import AppConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

class MainMenuConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main_menu'
    verbose_name = "Checkit"

    def ready(self):
        pass  # startup code here
        logging.info("Starting Checkit")
        # insert license check code here.
        # for now lets check adm but later lets check dongle.
