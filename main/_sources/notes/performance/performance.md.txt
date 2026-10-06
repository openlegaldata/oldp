# Performance Optimization Audit

This document identifies performance bottlenecks in OLDP and provides actionable,
code-level recommendations. Findings are organized by severity.

**Context:** OLDP serves legal documents (cases, laws, courts). Data is updated
approximately once per week, making it an excellent candidate for aggressive caching.

## Profiling Report

Measured profiling methodology and branch verification results (API + frontend + case detail) are documented in:

- [Performance Profiling Methodology and Findings (2026-02-22)](performance-profiling-2026-02-22.md)

Infrastructure-level tuning beyond Django (Gunicorn, Nginx, MariaDB, Elasticsearch, Redis, plus Docker Compose examples) is documented in:

- [Performance Optimization Beyond Django](performance-beyond-django.md)

---

## 1. Database Query Issues (HIGH)

### 1.1 N+1 Queries in `get_related()` Methods

**Cases** (`oldp/apps/cases/models.py:258-269`): `Case.get_related()` loops over
`RelatedCase` objects and accesses the `related_content` FK on each iteration,
triggering a separate query per related item.

**Laws** (`oldp/apps/laws/models.py:377-386`): Same pattern in `Law.get_related()`
with `RelatedLaw`.

**Fix:** Add `.select_related("related_content")` to the queryset in both methods:

```python
# cases/models.py — Case.get_related()
for item in RelatedCase.objects.filter(seed_content=self) \
        .select_related("related_content") \
        .order_by("-score")[:n]:
    items.append(item.related_content)

# laws/models.py — Law.get_related()
for item in RelatedLaw.objects.filter(seed_content=self) \
        .select_related("related_content") \
        .order_by("-score")[:n]:
    items.append(item.related_content)
```

### 1.2 N+1 in `get_content_as_html()`

`oldp/apps/cases/models.py:202-224` — Calls `get_reference_markers()` and
`get_markers()`, each triggering separate DB queries. This method is invoked on
every case detail page view (`oldp/apps/cases/views.py:91`).

**Fix:** Prefetch reference markers and annotation markers on the case queryset in
the detail view, or cache the rendered HTML output per case.

### 1.3 Inefficient `get_latest_law_book()`

`oldp/apps/laws/views.py:61-75` — Uses `len(candidates)` which forces full queryset
evaluation instead of using `.exists()` or `.first()`.

**Fix:**

```python
def get_latest_law_book(book_slug):
    candidate = LawBook.objects.filter(slug=book_slug, latest=True).first()
    if candidate is None:
        logger.info("Law book not found: %s", book_slug)
        raise Http404()
    # Check for duplicates (should not happen)
    count = LawBook.objects.filter(slug=book_slug, latest=True).count()
    if count > 1:
        logger.warning("Book has more than one instance with latest=true: %s", book_slug)
    return candidate
```

### 1.4 Uncached `Law.get_next()` and `has_next()`

`oldp/apps/laws/models.py:328-347` — Each call to `get_next()` or `has_next()`
triggers a separate DB query. When both are called (e.g., in templates), two
queries are executed for the same information.

**Fix:** Cache the result of `get_next()` on the instance and derive `has_next()`
from it:

```python
def get_next(self):
    if not hasattr(self, "_next_cache"):
        try:
            self._next_cache = Law.objects.get(previous=self.id)
        except Law.DoesNotExist:
            self._next_cache = None
        except Law.MultipleObjectsReturned:
            logger.error(f"Multiple laws found with previous={self.id}")
            self._next_cache = Law.objects.filter(previous=self.id).first()
    return self._next_cache

def has_next(self):
    return self.get_next() is not None
```

### 1.5 `Law.get_latest_revision_url()` — 2 DB Queries Per Call

`oldp/apps/laws/models.py:397-414` — Fetches the latest book and then checks for
law existence on every call. Particularly expensive if called in list contexts.

**Fix:** Cache on the instance, or avoid calling in list views entirely.

### 1.6 Missing `select_related` in API Views

| Location | Missing | Fix |
|---|---|---|
| `oldp/apps/laws/api_views.py:49-50` | `LawViewSet.get_queryset()` | Add `.select_related("book")` |
| `oldp/apps/annotations/api_views.py:32-33` | `AnnotationLabelViewSet.get_queryset()` | Add `.select_related("owner")` |
| `oldp/apps/annotations/api_views.py:62-64` | `CaseAnnotationViewSet` queryset | Add `"label__owner"` to existing `select_related` |

### 1.7 Missing `defer()` on Heavy Text Fields

| Location | Issue | Fix |
|---|---|---|
| `oldp/apps/laws/views.py:107` | `view_book()` loads all Law fields including `content` for list display | Add `.defer("content", "footnotes")` |
| `oldp/apps/laws/api_views.py:97` | `LawBookViewSet` loads `changelog`, `footnotes`, `sections` (large JSON) | Add `.defer("changelog", "footnotes", "sections")` for list action |
| `oldp/apps/laws/sitemaps.py:10-11` | `LawSitemap` queryset loads `content` | Add `.defer("content", "footnotes")` |

Note: `CaseSitemap` (`oldp/apps/cases/sitemaps.py:10-12`) correctly uses
`.defer(*Case.defer_fields_list_view)`.

---

## 2. Caching Gaps (HIGH)

### 2.1 Views Missing Cache Entirely

| View | Location | Impact |
|---|---|---|
| `CourtCasesListView` | `oldp/apps/courts/views.py:55-84` | DB queries on every page load |
| `CustomSearchView` | `oldp/apps/search/views.py:55-87` | Elasticsearch queries on every request |
| `autocomplete_view` | `oldp/apps/search/views.py:200-212` | New `SearchQuerySet` on every keystroke |

**Fix for `CourtCasesListView`:** Add `@method_decorator(cache_page(settings.CACHE_TTL))`
or use the `@cache_per_user` decorator.

**Fix for `autocomplete_view`:** Cache results by query string in Django's cache
framework:

```python
from django.core.cache import cache

def autocomplete_view(request):
    query = request.GET.get("q", "")
    cache_key = f"autocomplete:{query}"
    suggestions = cache.get(cache_key)
    if suggestions is None:
        try:
            sqs = SearchQuerySet().autocomplete(title=query)[:5]
            suggestions = [result.title for result in sqs]
        except Exception as e:
            logger.error("Autocomplete search failed: %s", str(e))
            suggestions = []
        cache.set(cache_key, suggestions, timeout=settings.CACHE_TTL)
    return JsonResponse({"results": suggestions})
```

### 2.2 API Endpoints with Insufficient or No Caching

| Endpoint | Location | Current | Recommended |
|---|---|---|---|
| Case API | `oldp/apps/cases/api_views.py:88` | 60 seconds | 15 minutes (`settings.CACHE_TTL`) |
| Law API | `oldp/apps/laws/api_views.py` | None | Add `cache_page(settings.CACHE_TTL)` on dispatch |
| LawBook API | `oldp/apps/laws/api_views.py` | None | Add `cache_page(settings.CACHE_TTL)` on dispatch |
| Court API | `oldp/api/views.py:19-43` | None | Add `cache_page(settings.CACHE_TTL)` on dispatch |
| City API | `oldp/api/views.py:91-97` | None | Add `cache_page(settings.CACHE_TTL)` on dispatch |
| State API | `oldp/api/views.py:100-106` | None | Add `cache_page(settings.CACHE_TTL)` on dispatch |

### 2.3 No Template Fragment Caching

Zero `{% cache %}` tags found across all templates. Static fragments like the
navbar, footer, and sidebar re-render on every request.

**Fix:** Wrap stable template fragments with Django's `{% cache %}` tag:

```html
{% load cache %}
{% cache 3600 navbar %}
  ... navbar HTML ...
{% endcache %}
```

### 2.4 Homepage Counts on Every Cache Miss

`oldp/apps/homepage/views.py:24-25` — `Law.objects.all().count()` and
`Case.get_queryset(request).count()` execute on every cache miss. The
`@cache_per_user` decorator mitigates this but each unique user still triggers
these queries.

**Fix:** Cache the counts separately with a longer TTL (e.g., 1 hour), since exact
counts are not critical:

```python
from django.core.cache import cache

laws_count = cache.get("homepage_laws_count")
if laws_count is None:
    laws_count = Law.objects.count()
    cache.set("homepage_laws_count", laws_count, timeout=3600)
```

---

## 3. Elasticsearch / Search (MEDIUM)

### 3.1 `datetime.now()` in Queryset

`oldp/apps/search/views.py:82` — `datetime.datetime.now()` is called on every
search request for the date facet end boundary.

**Fix:** Use a fixed date or compute it once per day via caching.

### 3.2 Heavy Facet Processing in Python

`oldp/apps/search/views.py:88-161` — `get_search_facets()` performs nested
iteration over facet data, building URL parameters in Python on every search
request.

**Fix:** Cache the facet processing result keyed by the query + selected facets
combination.

### 3.3 Autocomplete Without Caching

`oldp/apps/search/views.py:206` — Creates a new `SearchQuerySet()` per request
with no caching. See fix in section 2.1 above.

---

## 4. Middleware & HTTP (MEDIUM)

### 4.1 GZip Compression Disabled

`oldp/settings.py:138` — `GZipMiddleware` is commented out. Responses are sent
uncompressed, increasing transfer sizes.

**Fix:** Uncomment `'django.middleware.gzip.GZipMiddleware'` and place it first in
the middleware list. Alternatively, enable gzip at the reverse proxy level (nginx).

### 4.2 No Conditional Request Support

No `ConditionalGetMiddleware` is configured. The server cannot return `304 Not
Modified` for unchanged content, forcing full response re-transmission.

**Fix:** Add `'django.middleware.http.ConditionalGetMiddleware'` to `MIDDLEWARE`.

### 4.3 FlatpageFallbackMiddleware on Every 404

`oldp/settings.py:137` — `FlatpageFallbackMiddleware` triggers a DB query on every
404 response to check for a matching flatpage.

**Impact:** Low on most requests but adds latency on every 404 (bots, broken
links, etc.).

### 4.4 Static File Hashing Disabled

`oldp/settings.py:291` — `CompressedManifestStaticFilesStorage` (whitenoise) is
commented out. Static files are served without content hashes, preventing
long-lived browser cache headers.

**Fix:** Uncomment the whitenoise storage backend:

```python
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

---

## 5. Context Processor Overhead (LOW)

`oldp/apps/lib/context_processors.py:31` — `reverse("flatpages", ...)` is called on
every request to resolve the API info URL.

`oldp/apps/lib/context_processors.py:35` — `get_version()` is called on every
request.

**Fix:** Compute these once at module load time:

```python
_API_INFO_URL = None
_APP_VERSION = None

def global_context_processor(request):
    global _API_INFO_URL, _APP_VERSION
    if _API_INFO_URL is None:
        _API_INFO_URL = reverse("flatpages", kwargs={"url": "/api/"})
    if _APP_VERSION is None:
        _APP_VERSION = get_version()
    return {
        ...
        "api_info_url": _API_INFO_URL,
        "app_version": _APP_VERSION,
    }
```

---

## 6. SQL Injection Risk + Performance (LOW)

`oldp/apps/sources/views.py:43` — Raw SQL with Python string formatting:

```python
where_clause = ' WHERE c.created_date > "{}"'.format(diff_str)
```

This is a **SQL injection vulnerability**. Although `diff_str` is derived from
`datetime.timedelta`, the pattern is dangerous and should be replaced.

**Fix:** Use parameterized queries:

```python
if "delta" in date_range:
    diff = today - datetime.timedelta(**date_range["delta"])
    where_clause = " WHERE c.created_date > %s"
    params = [diff.strftime("%Y-%m-%d")]
else:
    where_clause = ""
    params = []

# ...
cursor.execute(query, params)
```

---

## 7. Deployment / Infrastructure Recommendations

### 7.1 Cache Backend

The default cache backend is file-based (`oldp/settings.py:255`). For production,
use Redis for significantly better performance:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379",
    }
}
```

### 7.2 Cache TTL

`CACHE_TTL = 60 * 15` (15 minutes) at `oldp/settings.py:254`. Given weekly data
updates, this could be extended to 1-4 hours for most views, with explicit cache
invalidation on data import.

### 7.3 Database Query Logging

Enable query logging in development to catch N+1 issues early:

```python
# settings_dev.py
LOGGING["loggers"]["django.db.backends"] = {
    "level": "DEBUG",
    "handlers": ["console"],
}
```

Or use `django-debug-toolbar` to inspect query counts per request.

---

## Summary — Priority Matrix

| Priority | Finding | Effort | Impact |
|---|---|---|---|
| HIGH | N+1 in `get_related()` (1.1) | Low | High — reduces queries from N+1 to 1 |
| HIGH | Missing caching on search views (2.1) | Low | High — ES queries are expensive |
| HIGH | API caching gaps (2.2) | Low | High — repeated identical API calls |
| HIGH | Missing `select_related` in API views (1.6) | Low | Medium — extra query per serialized object |
| HIGH | Missing `defer()` on heavy fields (1.7) | Low | Medium — reduces memory and transfer |
| MEDIUM | GZip compression disabled (4.1) | Low | Medium — reduces response sizes ~60-70% |
| MEDIUM | Static file hashing disabled (4.4) | Low | Medium — enables long-lived browser caching |
| MEDIUM | Search facet processing (3.2) | Medium | Medium — heavy Python on every search |
| MEDIUM | Template fragment caching (2.3) | Medium | Medium — avoids re-rendering static HTML |
| LOW | Context processor overhead (5) | Low | Low — minor per-request cost |
| LOW | SQL injection in sources (6) | Low | Low (security fix, staff-only view) |
| LOW | `get_latest_law_book` queryset eval (1.3) | Low | Low — minor per-request cost |
