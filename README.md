# OLDP: Open Legal Data Platform

[![Build Status](https://travis-ci.org/openlegaldata/oldp.svg?branch=master)](https://travis-ci.org/openlegaldata/oldp) [![Coverage Status](https://coveralls.io/repos/github/openlegaldata/oldp/badge.svg?branch=master)](https://coveralls.io/github/openlegaldata/oldp?branch=master)


OLDP written in Python 3 and based on Django web framework, used for processing legal content (court decisions and law text) and
providing a RESTful API and Elasticsearch-based search engine.

## Install

Requirements:
- Python3 with pip (virtualenv or conda)
- Database (Mysql, SQLite, ...)
- Elasticsearch
- `gcc` Some python libs
- `python-mysqldb`, `libmysqlclient-dev` use MySQL in Python
- `gettext` for Django locales with msguniq
- `pandoc` convert docbook to html (import GG)

```
# Create virtualenv
virtualenv -p python3 env
source env/bin/activate

# Install dependencies
apt-get install -y $(cat apt-requirements.txt)
pip install -r requirements.txt

# Prepare database
./manage.py migrate

# Prepare static files and localization (German and English)
./manage.py collectstatic --no-input
./manage.py compilemessages --l de --l en
```

## Run

Run the following command to start the web app at `localhost:8000`.

```
./manage.py runserver 8000
```

### Environment variables

You can override the settings from `oldp/settings.py` with environment variables:

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DATABASE_URL` | `mysql://oldp:oldp@127.0.0.1/oldp` | Path to database (usually mysql or sqlite) |
| `DJANGO_CONFIGURATION` | `Prod` | `Dev`, `Prod` or `Test` |
| `DJANGO_SECRET_KEY` | `None` | Set this in production mode |
| `DJANGO_ES_URL` | `http://localhost:9200/oldp` | Elasticsearch settings (host, port, index) |
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


## Issues

Please use our [GitHub issues](https://github.com/openlegaldata/oldp/issues) to report bugs, request feature or simply
leave some feedback.

## Contact

To contact Open Legal Data Platform, see here:

https://de.openlegaldata.io/contact/

## License

OLDP is licensed under the MIT License.
