#!/usr/bin/env bash

# mysql -u root -p"password" -h 127.0.0.1 -P 3307
export DATABASE_URL="mysql://root:password@127.0.0.1:3307/oldp_test"
export ES_URL="http://localhost:9200/oldp_test"