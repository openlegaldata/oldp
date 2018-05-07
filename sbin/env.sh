#!/usr/bin/env bash

# Add this to your scripts:
# export APP_ROOT=$(dirname "$(dirname "$0")")
# source $APP_ROOT/sbin/env.sh

source $APP_ROOT/env/bin/activate
cd $APP_ROOT
export PYTHONPATH="$PYTHONPATH:$APP_ROOT"

export DATABASE_URL="mysql://oldp:oldp@127.0.0.1/oldp"
export ES_URL="http://localhost:9200/oldp"

# requests[sockets] bug fix
unset all_proxy
