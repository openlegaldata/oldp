#!/usr/bin/env bash

# For large databases a direct mysql-dump is recommended
# mysqldump -u ${DATABASE_LOGIN} -p${DATABASE_PASSWORD} -h 127.0.0.1 --verbose ${DATABASE_NAME} | gzip > db.sql.gz

TYPE=$1
TODAY=$(date +'%Y-%m-%d')
DUMP_DIR=./workingdir/dumpdata/$TODAY

echo "Generating dump at $DUMP_DIR ..."

mkdir -p $DUMP_DIR

echo "Dumping public data"

python manage.py dumpdata courts -o $DUMP_DIR/courts.json
python manage.py dumpdata cases -o $DUMP_DIR/cases.json
python manage.py dumpdata laws -o $DUMP_DIR/laws.json
python manage.py dumpdata references -o $DUMP_DIR/references.json

if [[ $TYPE == "full" ]]
then
    echo "Including production data in dump..."

    python manage.py dumpdata sites -o $DUMP_DIR/sites.json
    python manage.py dumpdata flatpages -o $DUMP_DIR/flatpages.json
    python manage.py dumpdata auth -o $DUMP_DIR/auth.json
    python manage.py dumpdata authtoken -o $DUMP_DIR/authtoken.json
    python manage.py dumpdata accounts -o $DUMP_DIR/accounts.json

    OUT_FILE="oldp_dump.full.$TODAY.zip"

else
    OUT_FILE="oldp_dump.public.$TODAY.zip"
fi

echo "Zipping all the files.."

zip -r ./workingdir/$OUT_FILE $DUMP_DIR/*

echo "Cleaning dump dir..."

rm -r $DUMP_DIR

echo "Done."
