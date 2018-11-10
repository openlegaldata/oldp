#!/usr/bin/env bash

export APP_ROOT=$(dirname "$(dirname "$0")")
source $APP_ROOT/sbin/env.sh

export DJANGO_CONFIGURATION=Dev

python manage.py runserver

