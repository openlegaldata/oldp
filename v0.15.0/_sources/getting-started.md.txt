# Getting started

The following is a short guide on how to get started with OLDP.
If you encounter any problems, do not hesitate to open an issue or reach out on
[Discord](https://discord.gg/WCy3aq25ZF).

For the recommended containerised quickstart, see [Docker & Podman](docker.md).
For an overview of how the components fit together, see the
[Architecture overview](architecture.md).

## Install dependencies

Create a virtual environment and install the project (and its `dev`, `search`,
`processing` and `docs` extras) into it:

```
make venv
make install
```

System packages (compiler, MySQL client, GDAL, pandoc, gettext) are listed in
`apt_requirements.txt`:

```
apt-get install -y $(cat apt_requirements.txt)
```

## Run tests

Automated tests use [Django`s testing API](https://docs.djangoproject.com/en/2.1/topics/testing/).
If you are not familiar with Django have a look at their extensive documentation first.

For testing we use settings slightly different to development and production.
For instance, SQLite is used as database to speed up testing.
To use the testing settings, set the configuration variable as following:

```
export DJANGO_CONFIGURATION=TestConfiguration
```

Next, you can run either all or specific tests:

```
# use make command
make test

# call django manualy with all tests
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

- See [Docker](docker.md)

## Run server manually

Run webpack to create the website assets:

```
npm run-script build
```

Set the right environment:

```
export DJANGO_CONFIGURATION=DevConfiguration
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

## Configuration

OLDP is configured through environment variables and django-configurations
classes. See the [Configuration reference](configuration.md) for the full list
of settings, and [Deployment](deployment.md) when moving to production.
