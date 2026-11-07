# Sitemap XML

OLDP provides XML sitemaps to help search engines discover and index legal documents.
They are built with [Django's sitemaps framework](https://docs.djangoproject.com/en/stable/ref/contrib/sitemaps/),
but rendered to static files once a day instead of per request.

## Why static files

A sitemap page holds up to 50,000 URLs. With a full case corpus, rendering one
such page takes longer than the worker timeout (about 20 seconds for 50,000
cases), so a crawler fetching it on a cache miss would get a timeout. Rendering
the files in a scheduled job keeps that work out of the request path: serving
the sitemap is reading a file.

## Generating

```bash
python manage.py generate_sitemaps            # writes to settings.SITEMAP_ROOT
python manage.py generate_sitemaps -v 2       # also lists every file written
python manage.py generate_sitemaps --root /tmp/sitemaps --protocol http
```

Run it once a day (cron) and once after a deployment that changes the sitemap
code. Until it has run, `/sitemap.xml` returns 404.

- **Output directory:** `SITEMAP_ROOT`, default `MEDIA_ROOT / "sitemaps"`.
- **Domain:** taken from the current `Site` (`django.contrib.sites`, `SITE_ID`).
  Make sure its domain is the public host name, e.g. `de.openlegaldata.io`;
  the Django default is `example.com`.
- **Atomic:** every file is written to a temporary file and renamed into place.
  Pages are written before the index, so the index never lists a page that is
  not there yet. Pages left over from an earlier, larger run are deleted.
- **Stable pages:** sections are ordered by primary key, so rows added or
  updated while the job runs do not shift other rows between pages.

## Files and URLs

| File / URL | Description |
|-----|-------------|
| `/sitemap.xml` | Sitemap index listing every page below, with its newest `lastmod` |
| `/sitemap-court-<n>.xml` | Courts |
| `/sitemap-case-<n>.xml` | Court decisions |
| `/sitemap-law-<n>.xml` | Law sections (latest book revision only) |

`<n>` starts at 1. Django serves the files through `sitemap_file_view`
(`oldp/apps/lib/sitemaps.py`) with `Content-Type: application/xml`,
`Last-Modified` and `X-Robots-Tag: noindex`. In production the web server
should serve `SITEMAP_ROOT` directly, for example with nginx:

```nginx
# Before any regex location that matches *.xml.
location ~ ^/sitemap(-[a-z]+-[0-9]+)?\.xml$ {
    root /path/to/media/sitemaps;
    types { application/xml xml; }
}
```

## Sitemap sections

Only accepted content is listed: the sitemaps query as an anonymous user.

### CaseSitemap (`oldp/apps/cases/sitemaps.py`)

- **Queryset:** accepted cases, ordered by pk, loading only `slug` and `updated_date`.
- **Priority:** 1.0
- **Change frequency:** daily

### CourtSitemap (`oldp/apps/courts/sitemaps.py`)

- **Queryset:** accepted courts, ordered by pk.
- **Priority:** 0.6
- **Change frequency:** default (not set)

### LawSitemap (`oldp/apps/laws/sitemaps.py`)

- **Queryset:** accepted laws where `book__latest=True`, ordered by pk, loading
  only the law slug, book slug and `updated_date`.
- **Priority:** 0.9
- **Change frequency:** default (not set)

## robots.txt integration

The `Sitemap:` directive in `oldp/assets/templates/robots.txt` points search engine crawlers to the sitemap index. This is the standard mechanism for sitemap discovery (see [sitemaps.org](https://www.sitemaps.org/protocol.html#submit_robots)).
A deployment that serves its own robots.txt needs the same line.

## Submitting to search engines

Google retired its sitemap ping endpoint in 2023 and Django deprecated
`ping_google`. Submit `/sitemap.xml` once in Google Search Console and Bing
Webmaster Tools instead; both then re-fetch it on their own schedule.

## Adding a new sitemap section

1. Create a `sitemaps.py` file in the app (e.g., `oldp/apps/myapp/sitemaps.py`):

   ```python
   from django.contrib.sitemaps import GenericSitemap

   from oldp.apps.myapp.models import MyModel


   class MyModelSitemap(GenericSitemap):
       def __init__(self):
           super().__init__(
               {
                   "queryset": MyModel.objects.only("pk", "slug", "updated_date")
                   .order_by("pk"),
                   "date_field": "updated_date",
               },
               priority=0.5,
           )
   ```

2. Add it to `get_sitemaps()` in `oldp/apps/lib/sitemaps.py`:

   ```python
   return {
       "court": CourtSitemap(),
       "case": CaseSitemap(),
       "law": LawSitemap(),
       "mymodel": MyModelSitemap(),
   }
   ```

   The key (e.g., `"mymodel"`) names the files: `/sitemap-mymodel-<n>.xml`.
   Keys must be lower-case letters (see `FILENAME_RE`).

## Key files

- `oldp/apps/lib/sitemaps.py` — `get_sitemaps()`, `generate_sitemaps()`, `sitemap_file_view`
- `oldp/apps/homepage/management/commands/generate_sitemaps.py` — the management command
- `oldp/urls.py` — URL pattern for the sitemap files
- `oldp/apps/cases/sitemaps.py` — CaseSitemap
- `oldp/apps/courts/sitemaps.py` — CourtSitemap
- `oldp/apps/laws/sitemaps.py` — LawSitemap
- `oldp/assets/templates/robots.txt` — robots.txt with `Sitemap:` directive
- `oldp/apps/homepage/tests/test_sitemaps.py` — tests
