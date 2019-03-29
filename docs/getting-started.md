# Getting started

The following we present a short guide on how to get started with OLDP.
If you encounter any problems, do not hesitate to write an issue or contact us via email or [Twitter](https://twitter.com/openlegaldata).

## Install dependencies

```
apt-get install -y $(cat apt-requirements.txt)
pip install -r requirements.txt
npm install
```

## Run tests

Automated tests use [Django`s testing API](https://docs.djangoproject.com/en/2.1/topics/testing/).
If you are not familiar with Django have a look at their extensive documentation first.

For testing we use settings slightly different to development and production.
For instance, SQLite is used as database to speed up testing.
To use the testing settings, set the configuration variable as following:

```
export DJANGO_CONFIGURATION=Test
```

Next, you can run either all or specific tests:

```
# all tests
./manage.py test

# tests from the laws app
./manage.py test oldp.apps.laws.tests

# tests only views
./manage.py test --tag=views
```

Some tests require external services (Elasticsearch or web access).
To enable or disable them, set the configuration variables:

```
export DJANGO_TEST_WITH_ES=1
export DJANGO_TEST_WITH_WEB=0
```

## Docker

To get the dependency services (database, search, cache) running we suggest to use [Docker Compose](https://docs.docker.com/compose/).
Compose is a tool for defining and running multi-container Docker applications.
In order to use Docker Compose, you need to define a `docker-compose.yml` file as following:

```yaml
# docker-compose.yml
version: "3"
services:
  mysql:
    ports:
      - "3306:3306"
    container_name: mysql
    image: mariadb
    volumes:
      - ./data/mysql:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=password
      - MYSQL_DATABASE=oldp
      - MYSQL_USER=oldp
      - MYSQL_PASSWORD=oldp
  es:
    ports:
      - "9200:9200"
    container_name: es
    image: docker.elastic.co/elasticsearch/elasticsearch:5.4.0
    environment:
      - cluster.name=oldp
      - cluster.routing.allocation.disk.threshold_enabled=false
      - http.host=0.0.0.0
      - transport.host=127.0.0.1
      - xpack.security.enabled=false
    volumes:
      - ./data/es:/usr/share/elasticsearch/data

  redis:
    container_name: redis
    ports:
      - "6379:6379"
    image: redis:4.0.5-alpine
```

In the `docker-compose.yml` file we have defined three services `mysql`, `es` and `redis`.
Database and search data should be consistent. Hence, we mount directories from the local file system to the corresponding container.
The following commands create the directories and set permissions.

```
mkdir -p ./data/es
mkdir -p ./data/mysql
chmod 777 ./data/es
chmod 777 ./data/mysql
```

You have probably noticed that you set the login credentials for the MySQL database.
By default, Django is using the same settings.
But if you change those, you need to adjust the `DATABASE_URL` variable.

```
export DATABASE_URL="mysql://oldp:oldp@127.0.0.1/oldp"
```

Now you are ready to start the services:

```
docker-compose up
```

To stop the services run `docker-compose down` or press `CRTL+C`.

## Run server

Run webpack to create the website assets:

```
npm run-script build
```

Set the right environment:

```
export DJANGO_CONFIGURATION=Dev
```

Before running the server for the first time you need to set up the database schema and collect all static files to a single location.

```
./manage.py migrate
./manage.py collectstatic 
```

Now you are ready to go:

```
./manage.py runserver
```

An admin account can be created using:
```
./manage.py createsuperuser
```
