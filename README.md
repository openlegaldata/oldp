# OLDP: Open Legal Data Platform

> [!NOTE]
> We're back! This project is getting a fresh update - join us on [Discord](https://discord.gg/WCy3aq25ZF) to help revive it.

[![Documentation](https://img.shields.io/badge/docs-github--pages-blue)](https://openlegaldata.github.io/oldp/)
[![PyPI version](https://badge.fury.io/py/oldp.svg)](https://badge.fury.io/py/oldp)

OLDP is a Web application, written in Python 3.12 and based on the [Django web framework](https://www.djangoproject.com/),
It is used for processing legal text and providing a REST-API and Elasticsearch-based search engine.
OLDP is being develop by the non-profit initiative [Open Legal Data](https://openlegaldata.io/) with the goal
of building an Open Data platform for legal documents (mainly court decisions and laws).
The platform makes legal information freely accessible for the general public and especially third-party apps.

Our documentation is available [here](https://openlegaldata.github.io/oldp/).

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
[Getting started](https://openlegaldata.github.io/oldp/master/getting-started.html)

### Docker

To skip the whole installation procedure you can simply run OLDP as Docker (or Podman) container.
Steps:
1. Clone the repository `git clone https://github.com/openlegaldata/oldp`
2. Rename the local [env file (`local.env`)](local.env) to `.env`
3. Run `make up`, which will either call the `docker` or `podman` container engine depending on your setup
4. Navigate to [localhost:8000](http://localhost:8000) to view the site

A small tutorial on how to use OLDP with Docker can be found [here](https://openlegaldata.github.io/oldp/master/docker.html).

### Dependencies

Before anything else you will need to install the application dependencies.

- **Python 3.12** with pip (uv recommended)
- **Database (MySQL, SQLite, ...):** All database engines that support
  [Django's DB API](https://docs.djangoproject.com/en/2.1/ref/databases/) should work. MySQL is recommended.
- **Elasticsearch 7.17.x**: Our search engine backend. Other systems supported by [haystack](http://haystacksearch.org/)
  should also work.
- **gcc** Required to compile some Python libs
- **python-mysqldb, libmysqlclient-dev** if you choose MySQL as database
- **gettext** for Django locales with msguniq
- **pandoc** convert docbook to HTML (import GG)
- **GDAL**: Geospatial libraries used by the haystack search module (see
  [here](https://docs.djangoproject.com/en/2.1/ref/contrib/gis/install/geolibs/)).

```bash
# Create virtualenv with uv
uv venv --python 3.12
source .venv/bin/activate

# Clone repository to current directory
git clone https://github.com/openlegaldata/oldp.git .

# Install dependencies
apt-get install -y $(cat apt_requirements.txt)
uv pip install -e ".[dev]"
```

The first time you run OLDP, you will need to initialize the database with its default blank values. If you want
to run OLDP in production mode, you also need to prepare static files and localization.

```bash
# Prepare assets (JS, CSS, images, fonts, ...)
./manage.py compress

# Prepare database
./manage.py migrate

# Localization (German and English, needed for production)
./manage.py compilemessages --l de --l en

# Prepare static files (needed for production)
./manage.py collectstatic --no-input
```

## Run

Run the following command to start the web app at [http://localhost:8000/](http://localhost:8000/).

```bash
./manage.py runserver 8000
```

### Settings

The manage the app settings we rely on [django-configurations](https://django-configurations.readthedocs.io/en/stable/).
Pre-configured settings can be used by setting the `DJANGO_CONFIGURATION` environment variable to either `ProdConfiguration`, `DevConfiguration` or `TestConfiguration`.
You can as well override specific settings from `src/oldp/settings.py` with environment variables:

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_SETTINGS_MODULE` | `oldp.settings` | Tell  Django which settings file you want to use (in Python path syntax). |
| `DJANGO_CONFIGURATION` | `DevConfiguration` | Choice a predefined class of settings: `DevConfiguration`, `ProdConfiguration` or `TestConfiguration` |
| `DATABASE_URL` | `mysql://oldp:oldp@127.0.0.1/oldp` | Path to database (usually mysql or sqlite) |
| `DJANGO_SECRET_KEY` | `None` | Set this to a secret value in production mode |
| `DJANGO_ELASTICSEARCH_URL` | `http://localhost:9200/` | Elasticsearch settings (scheme, host, port) |
| `DJANGO_ELASTICSEARCH_INDEX` | `oldp` | Elasticsearch index name |
| `DJANGO_DEBUG` | `True` | Enable to show debugging messages and errors |
| `DJANGO_ADMINS` | `Admin,admin@openlegaldata.io` | Format: `Foo,foo@site.com;Bar,bar@site.com` |
| `DJANGO_SITE_URL` | `http://localhost:8000` | Canonical public base URL, used for absolute URLs and MCP OAuth discovery. Set to the HTTPS production origin, e.g. `https://de.openlegaldata.io`. |
| `DJANGO_ALLOWED_HOSTS` | `None` | Format: `foo.com,bar.net` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | (empty) | Trusted browser origins for CSRF and MCP Origin validation. Format: `https://de.openlegaldata.io,https://*.example.org` |
| `DJANGO_TOP_LAW_BOOKS` | (empty) | Comma-separated `LawBook` slugs surfaced as "top books" on `/law/`, in the order listed. Empty hides the top block. Example: `gg,bgb,stgb,hgb,estg` |
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
| `DJANGO_CACHE_DISABLE` | `False` | Set to `True` to disable cache (Redis) |
| `DJANGO_CACHE_BACKEND` | `file` | Cache backend selector. Set to `redis` to use `django-redis`. |
| `DJANGO_CACHE_TTL` | `21600` (6 h) | Default TTL in seconds for cached API and HTML views (`@cache_page(CACHE_TTL)`). |
| `DJANGO_CACHE_TTL_STATS` | `86400` (24 h) | TTL in seconds for stats endpoints, which aggregate over the full corpus. |
| `DJANGO_REDIS_URL` | `redis://127.0.0.1:6379/1` | Redis cache URL when `DJANGO_CACHE_BACKEND=redis`. |
| `DJANGO_FILE_CACHE_LOCATION` | `/var/tmp/django_cache` | File cache directory when `DJANGO_CACHE_BACKEND=file`; must be writable by the app. |
| `DJANGO_MCP_ANTHROPIC_ANON_RATE` | `500/hour` | Anonymous MCP request rate limit. Anthropic MCP IPs share a single anonymous bucket. |
| `DJANGO_MCP_USER_RATE` | `1000/hour` | Authenticated MCP request rate limit per user. |
| `DJANGO_ANON_CACHE_ENABLED` | `True` | Master switch for `AnonymousPublicCacheMiddleware` (strips `Vary: Cookie` / `Set-Cookie` and emits `Cache-Control: public` for anonymous GET/HEAD on public pages so a CDN can cache them). |
| `DJANGO_ANON_CACHE_PATH_PREFIXES` | `/case/,/law/,/court/,/pages/,/search/` | Comma-separated URL prefixes treated as anonymous-cacheable. |
| `DJANGO_ANON_CACHE_PATHS_EXACT` | `/` | Comma-separated exact paths treated as anonymous-cacheable (e.g. the homepage). |
| `DJANGO_ANON_CACHE_S_MAXAGE` | `600` | CDN edge TTL in seconds for anonymous public-cacheable responses. |
| `DJANGO_ANON_CACHE_MAX_AGE` | `60` | Browser TTL in seconds for anonymous public-cacheable responses. |



## Issues

Please use our [GitHub issues](https://github.com/openlegaldata/oldp/issues) to report bugs, request feature or simply
leave some feedback.

## Contact

To contact Open Legal Data Platform, see here:

https://de.openlegaldata.io/contact/

## Citation

Please cite the following [research paper](https://arxiv.org/abs/2005.13342), if you use our code or data:

```bibtex
@inproceedings{10.1145/3383583.3398616,
author = {Ostendorff, Malte and Blume, Till and Ostendorff, Saskia},
title = {Towards an Open Platform for Legal Information},
year = {2020},
isbn = {9781450375856},
publisher = {Association for Computing Machinery},
address = {New York, NY, USA},
url = {https://doi.org/10.1145/3383583.3398616},
doi = {10.1145/3383583.3398616},
booktitle = {Proceedings of the ACM/IEEE Joint Conference on Digital Libraries in 2020},
pages = {385–388},
numpages = {4},
keywords = {open data, open source, legal information system, legal data},
location = {Virtual Event, China},
series = {JCDL '20}
}
```

## License

OLDP is licensed under the MIT License.
