#!/usr/bin/env bash

# This script starts OLDP with gunicorn web server
# NOTE: production script is in other repo

# settings
export DJANGO_SETTINGS_MODULE=oldp.settings
export DJANGO_CONFIGURATION=Prod

# change to other theme settings
#export DJANGO_SETTINGS_MODULE=oldp_de.settings
#export DJANGO_CONFIGURATION=ProdDE

# Start your Django Unicorn
exec env/bin/gunicorn oldp.wsgi:application

