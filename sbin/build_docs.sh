#!/usr/bin/env bash

export APP_ROOT=$(dirname "$(dirname "$0")")
source $APP_ROOT/sbin/env.sh

cd docs
make html
