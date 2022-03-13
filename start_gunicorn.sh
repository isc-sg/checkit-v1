#!/bin/bash

PATH="/home/checkit/env/bin::/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin"

cd /home/checkit/camera_checker
/home/checkit/env/bin/gunicorn --keyfile /home/checkit/server.key --certfile /home/checkit/server.crt --bind 0.0.0.0:8000 camera_checker.wsgi

