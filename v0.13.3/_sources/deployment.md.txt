# Deployment

This guide covers running OLDP in production. For local development use
[Getting Started](getting-started.md); for the containerised quickstart see
[Docker & Podman](docker.md). All environment variables referenced here are
documented in the [Configuration reference](configuration.md).

## Overview

A production OLDP deployment consists of:

- the **OLDP app** (Django, served by an application server such as Gunicorn),
- a **relational database** (MariaDB/MySQL recommended),
- **Elasticsearch 7.17.x** for search,
- optionally **Redis** as the cache backend and a **CDN / reverse proxy**
  (e.g. Nginx) in front of the app.

The shipped `docker-compose.yaml` defines the `app`, `db` (MariaDB) and `search`
(Elasticsearch) services and is a good starting point for a single-host
deployment.

## Production configuration

Select the production settings class and provide the required secrets:

```bash
export DJANGO_CONFIGURATION=ProdConfiguration
export DJANGO_SECRET_KEY="<a long random secret>"
export DJANGO_ALLOWED_HOSTS="de.openlegaldata.io"
export DJANGO_SITE_URL="https://de.openlegaldata.io"
export DATABASE_URL="mysql://oldp:<password>@db/oldp"
export DJANGO_ELASTICSEARCH_URL="http://search:9200/"
```

When deploying the German site, point Django at the theme settings instead and
keep `DJANGO_CONFIGURATION` at the theme's production class (see
[The OLDP ecosystem](ecosystem.md#oldp-de-german-theme)):

```bash
export DJANGO_SETTINGS_MODULE=oldp_de.settings
export DJANGO_CONFIGURATION=ProdDEConfiguration
```

See the [Configuration reference](configuration.md) for caching (Redis), email,
MCP rate limits, logging and CDN cache settings.

## First-time setup

Prepare the database, assets and translations:

```bash
# Apply database migrations
./manage.py migrate

# Build front-end assets and collect static files
./manage.py compress
./manage.py collectstatic --no-input

# Compile translations (needed for production)
./manage.py compilemessages --l de --l en

# Build the search index
./manage.py rebuild_index
```

With Docker Compose the equivalent steps are available as Make targets
(`make migrate`, `make rebuild-index`, `make compile-locale`).

Create an administrator account:

```bash
./manage.py createsuperuser
```

## Deploying updates

When rolling out new code:

1. Back up the database (and review test/CI status before deploying).
2. Pull the new code or container image.
3. Run `./manage.py migrate` for any schema changes.
4. Rebuild assets if they changed: `./manage.py compress` and
   `./manage.py collectstatic --no-input`.
5. Run `./manage.py update_index` (incremental) or `./manage.py rebuild_index`
   (full) if search mappings changed.
6. Restart the application server.

## Production checklist

- [ ] `DJANGO_CONFIGURATION=ProdConfiguration` (or the theme's prod class)
- [ ] `DJANGO_SECRET_KEY` set to a strong, secret value
- [ ] `DJANGO_DEBUG=False` (implied by the prod configuration)
- [ ] `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` restricted to your
      domains
- [ ] `DJANGO_SITE_URL` set to the public HTTPS origin (also used for MCP OAuth
      discovery)
- [ ] Database backups configured
- [ ] Elasticsearch reachable and index built
- [ ] TLS terminated at the proxy/CDN; static files served efficiently
- [ ] Cache backend chosen (`DJANGO_CACHE_BACKEND=redis` for multi-process
      deployments)

## Operations

- [Elasticsearch](elasticsearch.md) — reindexing, realtime sync, index fields.
- [Sitemaps](sitemap-xml.md) — XML sitemaps and search-engine pinging.
- [Data Dumps & Bulk Downloads](data-dumps.md) — exporting snapshots with
  `dump_api_data`.

## Going further

For tuning the application server, reverse proxy, database, Elasticsearch and
Redis beyond Django defaults, see the internal
[Performance notes](notes/index.md). These are engineering notes rather than a
prescriptive configuration — benchmark against your own traffic.
