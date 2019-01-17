#!/usr/bin/env bash

# Add this to your scripts:
# export APP_ROOT=$(dirname "$(dirname "$0")")
# source $APP_ROOT/sbin/env.sh

source $APP_ROOT/env/bin/activate
cd $APP_ROOT
export PYTHONPATH="$PYTHONPATH:$APP_ROOT"

# requests[sockets] bug fix
unset all_proxy
