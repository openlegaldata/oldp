#!/usr/bin/env bash

# Call these commands before starting production server

# Statics
python manage.py collectstatic --noinput

# Locale
python manage.py makemessages --locale=de --ignore=env --ignore=workingdir
python manage.py compilemessages --l de --l en