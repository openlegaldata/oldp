# Configuration reference

OLDP is configured through [django-configurations](https://django-configurations.readthedocs.io/en/stable/).
Settings live in `src/oldp/settings.py` and are grouped into predefined
configuration classes selected with the `DJANGO_CONFIGURATION` environment
variable. Most individual settings can additionally be overridden through
environment variables (all prefixed with `DJANGO_`).

This page is the **single source of truth** for OLDP's environment variables.
Other pages (the [README](https://github.com/openlegaldata/oldp#readme),
[Getting Started](getting-started.md), [Deployment](deployment.md)) link here
rather than restating the table.

## Configuration classes

Set `DJANGO_CONFIGURATION` to one of:

| Class | Use case |
| ----- | -------- |
| `DevConfiguration` | Local development (default). `DEBUG=True`, verbose logging. |
| `ProdConfiguration` | Production. Requires `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, etc. |
| `TestConfiguration` | Automated tests. Uses SQLite and a mock Elasticsearch backend by default. |

```bash
export DJANGO_SETTINGS_MODULE=oldp.settings
export DJANGO_CONFIGURATION=DevConfiguration
```

When running with the German theme, point `DJANGO_SETTINGS_MODULE` at the theme
package instead — see [The OLDP ecosystem](ecosystem.md) and the
[oldp-de](https://github.com/openlegaldata/oldp-de) project.

## Core / Django

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_SETTINGS_MODULE` | `oldp.settings` | Tells Django which settings file to use (Python path syntax). |
| `DJANGO_CONFIGURATION` | `DevConfiguration` | Predefined settings class: `DevConfiguration`, `ProdConfiguration` or `TestConfiguration`. |
| `DJANGO_SECRET_KEY` | `None` | Set this to a secret value in production mode. |
| `DJANGO_DEBUG` | `True` | Enable to show debugging messages and errors. |
| `DJANGO_ADMINS` | `Admin,admin@openlegaldata.io` | Format: `Foo,foo@site.com;Bar,bar@site.com` |
| `DJANGO_SITE_URL` | `http://localhost:8000` | Canonical public base URL, used for absolute URLs and MCP OAuth discovery. Set to the HTTPS production origin, e.g. `https://de.openlegaldata.io`. |
| `DJANGO_ALLOWED_HOSTS` | `None` | Format: `foo.com,bar.net` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | (empty) | Trusted browser origins for CSRF and MCP Origin validation. Format: `https://de.openlegaldata.io,https://*.example.org` |
| `DJANGO_LANGUAGES_DOMAINS` | | Format: `{'de.foo.com':'de','fr.foo.com':'fr'}` |
| `DJANGO_TIME_ZONE` | `UTC` | Time zone. |
| `DJANGO_TOP_LAW_BOOKS` | (empty) | Comma-separated `LawBook` slugs surfaced as "top books" on `/law/`, in the order listed. Empty hides the top block. Example: `gg,bgb,stgb,hgb,estg` |

## Database

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DATABASE_URL` | `mysql://oldp:oldp@127.0.0.1/oldp` | Database connection (usually MySQL or SQLite). |

## Elasticsearch

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_ELASTICSEARCH_URL` | `http://localhost:9200/` | Elasticsearch connection (scheme, host, port). |
| `DJANGO_ELASTICSEARCH_INDEX` | `oldp` | Elasticsearch index name. |

See [Elasticsearch](elasticsearch.md) for index management and reindexing.

## Caching (Redis / file cache)

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_CACHE_DISABLE` | `False` | Set to `True` to disable cache (Redis). |
| `DJANGO_CACHE_BACKEND` | `file` | Cache backend selector. Set to `redis` to use `django-redis`. |
| `DJANGO_CACHE_TTL` | `21600` (6 h) | Default TTL in seconds for cached API and HTML views (`@cache_page(CACHE_TTL)`). |
| `DJANGO_CACHE_TTL_STATS` | `86400` (24 h) | TTL in seconds for stats endpoints, which aggregate over the full corpus. |
| `DJANGO_REDIS_URL` | `redis://127.0.0.1:6379/1` | Redis cache URL when `DJANGO_CACHE_BACKEND=redis`. |
| `DJANGO_FILE_CACHE_LOCATION` | `/var/tmp/django_cache` | File cache directory when `DJANGO_CACHE_BACKEND=file`; must be writable by the app. |

## Anonymous CDN cache

These tune `AnonymousPublicCacheMiddleware`, which makes anonymous public pages
CDN-cacheable.

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_ANON_CACHE_ENABLED` | `True` | Master switch for `AnonymousPublicCacheMiddleware` (strips `Vary: Cookie` / `Set-Cookie` and emits `Cache-Control: public` for anonymous GET/HEAD on public pages so a CDN can cache them). |
| `DJANGO_ANON_CACHE_PATH_PREFIXES` | `/case/,/law/,/court/,/pages/,/search/` | Comma-separated URL prefixes treated as anonymous-cacheable. |
| `DJANGO_ANON_CACHE_PATHS_EXACT` | `/` | Comma-separated exact paths treated as anonymous-cacheable (e.g. the homepage). |
| `DJANGO_ANON_CACHE_S_MAXAGE` | `600` | CDN edge TTL in seconds for anonymous public-cacheable responses. |
| `DJANGO_ANON_CACHE_MAX_AGE` | `60` | Browser TTL in seconds for anonymous public-cacheable responses. |

## MCP server

See [MCP Server](mcp.md) for the full tool catalogue.

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_MCP_ANTHROPIC_ANON_RATE` | `500/hour` | Anonymous MCP request rate limit. Anthropic MCP IPs share a single anonymous bucket. |
| `DJANGO_MCP_USER_RATE` | `1000/hour` | Authenticated MCP request rate limit per user. |

## Email

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_DEFAULT_FROM_EMAIL` | `no-reply@openlegaldata.io` | Emails are sent from this address. |
| `DJANGO_EMAIL_HOST` | `localhost` | SMTP server. |
| `DJANGO_EMAIL_HOST_USER` | | SMTP user. |
| `DJANGO_EMAIL_HOST_PASSWORD` | | SMTP password. |
| `DJANGO_EMAIL_USE_TLS` | `False` | Enable TLS. |
| `DJANGO_EMAIL_PORT` | `25` | SMTP port. |
| `DJANGO_FEEDBACK_EMAIL` | `feedback@openlegaldata.io` | Messages from the feedback widget are sent to this address. |

## Logging

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_LOG_FILE` | `oldp.log` | Name of log file (in the logs directory). |
| `DJANGO_LOG_MAX_BYTES` | `15728640` | Max size of `oldp.log` before rotation, in bytes (default 15 MB). Raise in production if rotation churns through history faster than you can analyze it. |
| `DJANGO_LOG_BACKUP_COUNT` | `10` | Number of rotated backups (`oldp.log.1` … `oldp.log.N`) to retain. Total disk usage is roughly `DJANGO_LOG_MAX_BYTES × (DJANGO_LOG_BACKUP_COUNT + 1)`. |

## Testing

| Variable name | Default value | Comment |
| ------------- | ------------- | ------- |
| `DJANGO_TEST_WITH_ES` | `False` | Run tests that require Elasticsearch. |
| `DJANGO_TEST_WITH_WEB` | `False` | Run tests that require web access. |

See [Testing](testing.md) for how these interact with the test configuration.
