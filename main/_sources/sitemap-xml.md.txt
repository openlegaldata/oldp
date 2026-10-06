# Sitemap XML

OLDP provides an XML sitemap to help search engines discover and index legal documents.
The sitemap is built using [Django's sitemaps framework](https://docs.djangoproject.com/en/stable/ref/contrib/sitemaps/).

## Available URLs

| URL | Description |
|-----|-------------|
| `/sitemap.xml` | Sitemap index listing all section sitemaps |
| `/sitemap-case.xml` | All court decisions |
| `/sitemap-court.xml` | All courts |
| `/sitemap-law.xml` | All laws (latest version only) |

## Sitemap sections

### CaseSitemap (`oldp/apps/cases/sitemaps.py`)

- **Queryset:** All cases ordered by `updated_date` (descending), with `court` pre-fetched and list-view fields deferred.
- **Priority:** 1.0
- **Change frequency:** daily

### CourtSitemap (`oldp/apps/courts/sitemaps.py`)

- **Queryset:** All courts ordered by `updated_date` (descending).
- **Priority:** 0.6
- **Change frequency:** default (not set)

### LawSitemap (`oldp/apps/laws/sitemaps.py`)

- **Queryset:** Laws where `book__latest=True`, with `content` and `footnotes` deferred, ordered by `updated_date` (descending).
- **Priority:** 0.9
- **Change frequency:** default (not set)

## Caching

Both the sitemap index and section sitemaps are cached for 24 hours (`cache_page(86400)`) to avoid expensive database queries on every request. See `oldp/urls.py` for the URL configuration.

## robots.txt integration

The `Sitemap:` directive in `oldp/assets/templates/robots.txt` points search engine crawlers to the sitemap index. This is the standard mechanism for sitemap discovery (see [sitemaps.org](https://www.sitemaps.org/protocol.html#submit_robots)).

## Pinging Google

After adding or updating content, you can notify Google about the updated sitemap:

```bash
.venv/bin/python manage.py ping_google /sitemap.xml
```

## Adding a new sitemap section

1. Create a `sitemaps.py` file in the app (e.g., `oldp/apps/myapp/sitemaps.py`):

   ```python
   from django.contrib.sitemaps import GenericSitemap

   from oldp.apps.myapp.models import MyModel


   class MyModelSitemap(GenericSitemap):
       def __init__(self):
           super().__init__(
               {
                   "queryset": MyModel.objects.all().order_by("-updated_date"),
                   "date_field": "updated_date",
               },
               priority=0.5,
           )
   ```

2. Register the sitemap in `oldp/urls.py` by adding it to the `sitemaps` dict:

   ```python
   from oldp.apps.myapp.sitemaps import MyModelSitemap

   sitemaps = {
       "court": CourtSitemap(),
       "case": CaseSitemap(),
       "law": LawSitemap(),
       "mymodel": MyModelSitemap(),
   }
   ```

   The key (e.g., `"mymodel"`) determines the section URL: `/sitemap-mymodel.xml`.

## Key files

- `oldp/urls.py` — sitemap URL configuration and `sitemaps` dict
- `oldp/apps/cases/sitemaps.py` — CaseSitemap
- `oldp/apps/courts/sitemaps.py` — CourtSitemap
- `oldp/apps/laws/sitemaps.py` — LawSitemap
- `oldp/assets/templates/robots.txt` — robots.txt with `Sitemap:` directive
- `oldp/apps/homepage/tests/test_views.py` — sitemap integration test
