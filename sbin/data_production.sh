#!/usr/bin/env bash

# This script includes all commands that need to be executed to load all data for production setup

# Super user
# python manage.py createsuperuser --username ... --email ...

# law.count =
# lawbook.count =
python manage.py process_laws --empty --min-lines 1000 --input ../gesetze-tools/laws --es --es-setup
python manage.py import_grundgesetz --empty

python manage.py set_law_book_order
python manage.py set_law_book_revision

# courts
python manage.py import_courts --empty oldp/apps/courts/data/ecli.csv
python manage.py enrich_courts

# cases
#python manage.py process_cases --limit 20 --empty
# You exceeded your API limit
# grep -lir 'You exceeded your API limit' split003/* | xargs mv -t _invalid/

#python manage.py process_cases --limit 0 --empty --input /var/www/apps/oldp/data/bverfg
python manage.py process_cases --limit 0 --empty --input /var/www/apps/oldp/data/private/cases_bverfg_cron/

python manage.py process_cases --limit 0 --input /var/www/apps/oldp/data/split001
python manage.py process_cases --limit 0 --input /var/www/apps/oldp/data/split002
python manage.py process_cases --limit 0 --input /var/www/apps/oldp/data/split003
python manage.py process_cases --limit 0 --input /var/www/apps/oldp/data/split004
python manage.py process_cases --limit 0 --input /var/www/apps/oldp/data/split005_tor



# python manage.py process_cases --limit 20 --input workingdir/cases_openjur_cron


# related
python manage.py generate_related case
python manage.py generate_related law