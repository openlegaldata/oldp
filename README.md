# OLDP: Open Legal Data Platform

OLDP written in Python 3 and based on Django web framework, used for processing legal content (cases and law) and
providing a RESTful API and Elasticsearch-based search engine.

## Install

Requirements:
- Python3 with pip, Virtualenv
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
| `DJANGO_SECRET_KEY` | `None` | Set this in production mode |
| `DJANGO_ES_URL` | `http://localhost:9200/oldp` | Elasticsearch |
| `DJANGO_DEBUG` | `True` | Dev or production |
| `DJANGO_ADMINS` | `Admin,admin@openlegaldata.io` | Format: `Foo,foo@site.com;Bar,bar@site.com` |
| `DJANGO_ALLOWED_HOSTS` | `None` | Format: `foo.com,bar.net` |
| `DJANGO_LANGUAGES_DOMAINS` | | Format: `{'de.foo.com':'de','fr.foo.com':'fr'}` |
| `DJANGO_DEFAULT_FROM_EMAIL` | `no-reply@openlegaldata.io` | |
| `DJANGO_EMAIL_HOST` | `localhost` | ... |
| `DJANGO_EMAIL_HOST_USER` | | |
| `DJANGO_EMAIL_HOST_PASSWORD` | | |
| `DJANGO_FEEDBACK_EMAIL` | `feedback@openlegaldata.io` | Messages from feedback widget are sent to this address. |
| `DJANGO_IMPRINT_NAME` | | |
| `DJANGO_IMPRINT_STREET` | | |
| `DJANGO_IMPRINT_CITY` | | |
| `DJANGO_IMPRINT_EMAIL` | | |
| `DJANGO_IMPRINT_PHONE` | | |
| `DJANGO_TIME_ZONE` | `UTC` | |
| `DJANGO_TEST_WITH_ES` | `False` | Run tests that require Elasticsearch |
| `DJANGO_TEST_WITH_WEB` | `False` | Run tests that require web access |


## Contact

To contact Open Legal Data Platform, see here:

https://de.openlegaldata.io/contact/

## License

OLDP is licensed under the MIT License.
