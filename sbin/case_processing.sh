#!/usr/bin/env bash

export APP_ROOT=$(dirname "$(dirname "$0")")
source $APP_ROOT/sbin/env.sh

python processing/case juris --input=workingdir/batch1/input/ --output=workingdir/batch1/processed/ \
    --storage=fs \
    --post=move \
    --post-move-path=workingdir/batch1/backup/ \
    --verbose

# python processing/case juris --input=workingdir/batch1/input/ --output=workingdir/batch1/processed/ --storage=fs --post=keep --limit=1000 --verbose > processing.log
