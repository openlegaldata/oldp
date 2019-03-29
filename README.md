# OLDP: Open Legal Data Platform

[![Build Status](https://travis-ci.org/openlegaldata/oldp.svg?branch=master)](https://travis-ci.org/openlegaldata/oldp)
[![Coverage Status](https://coveralls.io/repos/github/openlegaldata/oldp/badge.svg?branch=master)](https://coveralls.io/github/openlegaldata/oldp?branch=master)
[![Documentation Status](https://readthedocs.org/projects/oldp/badge/?version=latest)](https://oldp.readthedocs.io/en/latest/?badge=latest)
[![PyPI version](https://badge.fury.io/py/oldp.svg)](https://badge.fury.io/py/oldp)

OLDP is a web application, written in Python 3.5 and based on the [Django web framework](https://www.djangoproject.com/),
It is used for processing legal text and providing a REST-API and Elasticsearch-based search engine.
OLDP is being develop by the non-profit initiative [Open Legal Data](https://openlegaldata.io/) with the goal
of building an Open Data platform for legal documents (mainly court decisions and laws).
The platform makes legal information freely accessible for the general public and especially third-party apps.

Our documentation is available [here](https://oldp.readthedocs.io/).

## Demo

[![Live demo](https://github.com/openlegaldata/oldp/raw/master/docs/_static/screenshot.sm.png)](https://github.com/openlegaldata/oldp/raw/master/docs/_static/screenshot.png)

A live demo is available [here](https://de.openlegaldata.io/) (in German).

## Features

- **Cases**: Court decisions with meta data and content in HTML.
- **Laws**: Full-text laws and regulations and their corresponding case-law.
- **Courts**: Browse courts organized by states, jurisdiction and level of appeal from your country.
- **Search**: A document search engine based on Elasticsearch/Haystack supporting most common search syntax and faceting.
- **API**: Adding, updating, retrieving and deleting data through CRUD REST API based on [DRF](https://www.django-rest-framework.org/) including
    auto-generated API clients from Swagger.
- **Themes**: Easily adjust the look and feel depending on your countries needs (see [German theme](https://github.com/openlegaldata/oldp-de)).

## Installation guide

Before you can use OLDP, you’ll need to get it installed.
For a more detailed guide on how to get started with OLDP have a look at:
[Getting started](https://oldp.readthedocs.io/en/latest/getting-started.html)

### Docker

To skip the whole installation procedure you can simply run OLDP as Docker container.
Just `git clone` the repository first and then start everything with a `docker-compose up` from within the repository directory.
A small tutorial on how to use OLDP with Docker can be found [here](https://oldp.readthedocs.io/en/latest/docker.html).

### Dependencies

Before anything else you will need to install the application dependencies.

- **Python 3.5** with pip (virtualenv or conda recommended)
- **Node JS 8.12.x** with npm for building JS dependencies
- **Database (MySQL, SQLite, ...):** All database engines that support
  [Django's DB API](https://docs.djangoproject.com/en/2.1/ref/databases/) should work. MySQL is recommended.
- **Elasticsearch 5.4.x**: Our search engine backend. Other systems supported by [haystack](http://haystacksearch.org/)
  should also work.
- **Redis 4.x**: Caching engine (optional)
- **gcc** Required to compile some Python libs
- **python-mysqldb, libmysqlclient-dev** if you choose MySQL as database
- **gettext** for Django locales with msguniq
- **pandoc** convert docbook to HTML (import GG)
- **GDAL**: Geospatial libraries used by the haystack search module (see
  [here](https://docs.djangoproject.com/en/2.1/ref/contrib/gis/install/geolibs/)).

```
# Create virtualenv
virtualenv -p python3 env
source env/bin/activate

# Clone repository to current directory
git clone https://github.com/openlegaldata/oldp.git .

# Install dependencies
apt-get install -y $(cat apt-requirements.txt)
pip install -r requirements.txt
npm install
```

The first time you run OLDP, you will need to initialize the database with its default blank values. If you want
to run OLDP in production mode, you also need to prepare static files and localization.

```
# Prepare assets (JS, CSS, images, fonts, ...)
npm run-script build

# Prepare database
./manage.py migrate

# Localization (German and English, needed for production)
./manage.py compilemessages --l de --l en

# Prepare static files (needed for production)
./manage.py collectstatic --no-input

```

## Run

Run the following command to start the web app at [http://localhost:8000/](http://localhost:8000/).

```
./manage.py runserver 8000
```

### Settings

The manage the app settings we rely on [django-configurations](https://django-configurations.readthedocs.io/en/stable/).
Pre-configured settings can be used by setting the `DJANGO_CONFIGURATION` environment variable to either `Prod`, `Dev` or `Test`.
You can as well override specific settings from `oldp/settings.py` with environment variables:

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_SETTINGS_MODULE` | `oldp.settings` | Tell  Django which settings file you want to use (in Python path syntax). |
| `DJANGO_CONFIGURATION` | `Prod` | Choice a predefined class of settings: `Dev`, `Prod` or `Test` |
| `DATABASE_URL` | `mysql://oldp:oldp@127.0.0.1/oldp` | Path to database (usually mysql or sqlite) |
| `DJANGO_SECRET_KEY` | `None` | Set this to a secret value in production mode |
| `DJANGO_ELASTICSEARCH_URL` | `http://localhost:9200/` | Elasticsearch settings (scheme, host, port) |
| `DJANGO_ELASTICSEARCH_INDEX` | `oldp` | Elasticsearch index name |
| `DJANGO_DEBUG` | `True` | Enable to show debugging messages and errors |
| `DJANGO_ADMINS` | `Admin,admin@openlegaldata.io` | Format: `Foo,foo@site.com;Bar,bar@site.com` |
| `DJANGO_ALLOWED_HOSTS` | `None` | Format: `foo.com,bar.net` |
| `DJANGO_LANGUAGES_DOMAINS` | | Format: `{'de.foo.com':'de','fr.foo.com':'fr'}` |
| `DJANGO_DEFAULT_FROM_EMAIL` | `no-reply@openlegaldata.io` | Emails are sent from this address |
| `DJANGO_EMAIL_HOST` | `localhost` | SMTP server |
| `DJANGO_EMAIL_HOST_USER` | | SMTP user |
| `DJANGO_EMAIL_HOST_PASSWORD` | | SMTP password |
| `DJANGO_EMAIL_USE_TLS` | `False` | enable TLS |
| `DJANGO_EMAIL_PORT` | `25` | SMTP port |
| `DJANGO_FEEDBACK_EMAIL` | `feedback@openlegaldata.io` | Messages from feedback widget are sent to this address. |
| `DJANGO_TIME_ZONE` | `UTC` | Time zone |
| `DJANGO_TEST_WITH_ES` | `False` | Run tests that require Elasticsearch |
| `DJANGO_TEST_WITH_WEB` | `False` | Run tests that require web access |
| `DJANGO_LOG_FILE` | `oldp.log` | Name of log file (in logs directory) |
| `DJANGO_DISABLE_CACHE` | `False` | Set to `True` to disable cache (Redis) |



## Issues

Please use our [GitHub issues](https://github.com/openlegaldata/oldp/issues) to report bugs, request feature or simply
leave some feedback.

## Contact

To contact Open Legal Data Platform, see here:

https://de.openlegaldata.io/contact/

## License

OLDP is licensed under the MIT License.
