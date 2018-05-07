#!/usr/bin/env bash

export APP_ROOT=$(dirname "$(dirname "$0")")
source $APP_ROOT/sbin/env.sh
source $APP_ROOT/sbin/test_env.sh

#echo "${@}"

# Use env var ES_UNITTEST=1 to enable Elasticsearch unit testing (default: disabled)

#export OLDP_TEST_LOG_LEVEL="info"

# run tests the django way!
#python -m unittest discover test

# Run all the tests in the animals.tests module
#$ ./manage.py test animals.tests

# Run all the tests found within the 'animals' package
#$ ./manage.py test animals

# Run just one test case
#$ ./manage.py test animals.tests.AnimalTestCase

# Run just one test method
#$ ./manage.py test animals.tests.AnimalTestCase.test_animals_can_speak

./manage.py test ${@}