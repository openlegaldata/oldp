#!/usr/bin/env bash

mkdir workingdir
cd workingdir
git clone git@github.com:bundestag/gesetze-tools.git
cd gesetze-tools
virtualenv -p python env
source env/bin/activate
pip install -r requirements.txt
python lawde.py loadall
