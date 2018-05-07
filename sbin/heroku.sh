#!/usr/bin/env bash

# Run this script the write demo data to Heroku

export APP_ROOT=$(dirname "$(dirname "$0")")
source $APP_ROOT/sbin/env.sh

ES_URL="http://localhost:9200"

python processing/case juris --path=$APP_ROOT/test/resources/juris --es-url=$ES_URL --override-index --verbose
python processing/case openjur --path=$APP_ROOT/test/resources/openjur --es-url=$ES_URL --verbose
python processing/law --path=$APP_ROOT/test/resources/law --es-url=$ES_URL

# Set Heroku config
# $ heroku config:set ES_URL=https://...
