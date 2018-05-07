#!/usr/bin/env bash

export APP_ROOT=$(dirname "$(dirname "$0")")
source $APP_ROOT/sbin/env.sh

# Super user
python manage.py createsuperuser --username admin


# laws
python manage.py import_grundgesetz --limit 10
python manage.py process_laws --limit 100 --min-lines 1000 --input workingdir/gesetze-tools/laws

# courts
python manage.py import_courts --empty apps/courts/data/ecli.csv
python manage.py enrich_courts

# cases
python manage.py process_cases --limit 20 --empty
# ./manage.py process_cases --limit 0 --empty --input workingdir/bverfg
# python manage.py process_cases --limit 20 --input workingdir/cases_openjur_cron


# related
python manage.py generate_related case
python manage.py generate_related law

