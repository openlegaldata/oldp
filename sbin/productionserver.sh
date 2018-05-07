#!/usr/bin/env bash

# Run as in production
# with gunicorn
# ...

export APP_ROOT=$(dirname "$(dirname "$0")")
source $APP_ROOT/sbin/env.sh

export DJANGO_DEBUG=false

source $APP_ROOT/sbin/prepare_production.sh

python manage.py runserver