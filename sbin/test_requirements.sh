#!/usr/bin/env bash


virtualenv -p python3.5 workingdir/test_env
source workingdir/test_env/bin/activate
pip install -r requirements.txt
pip freeze

# clean up again
rm -r workingdir/test_env
