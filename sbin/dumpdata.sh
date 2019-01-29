#!/usr/bin/env bash

# For large databases a direct mysql-dump is recommended
# mysqldump -u ${DATABASE_LOGIN} -p${DATABASE_PASSWORD} -h 127.0.0.1 --verbose ${DATABASE_NAME} | gzip > db.sql.gz

export DIR=workingdir/dumpdata

mkdir $DIR

python manage.py dumpdata sites -o $DIR/sites.json
python manage.py dumpdata flatpages -o $DIR/flatpages.json
python manage.py dumpdata auth -o $DIR/auth.json
python manage.py dumpdata authtoken -o $DIR/authtoken.json

python manage.py dumpdata accounts -o $DIR/accounts.json
python manage.py dumpdata courts -o $DIR/courts.json
python manage.py dumpdata cases -o $DIR/cases.json
python manage.py dumpdata laws -o $DIR/laws.json
python manage.py dumpdata references -o $DIR/references.json


zip -r workingdir/dumpdata.zip $DIR/sites.json $DIR/flatpages.json $DIR/auth.json $DIR/authtoken.json $DIR/accounts.json \
    $DIR/courts.json $DIR/cases.json $DIR/laws.json $DIR/references.json

rm -r $DIR
