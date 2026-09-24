# Performance Profiling Methodology and Findings (2026-02-22)

This document summarizes the profiling methodology and findings for the current feature branch performance work, including cache correctness fixes, API caching verification, and frontend/case-page profiling.

## Scope

Profiled and verified:

- API endpoints:
  - `/api/`
  - `/api/cases/`
  - `/api/laws/`
  - `/api/law_books/`
- Frontend pages:
  - `/` (frontpage)
  - `/case/` (case list)
  - `/case/foo-case` (case detail, fixture data)

The work included both correctness fixes (cache variance/safety) and performance improvements (query reductions, caching).

## Environment and Tooling

- Date: **February 22, 2026**
- Python env: `.venv`
- Profiling packages installed with `uv`:
  - `django-silk`
  - `django-querycount`
  - `gprof2dot`

### Commands used to install profiling packages

```bash
source .venv/bin/activate
uv pip install django-silk==5.4.3 django-querycount==0.8.3 gprof2dot
```

## Important Runtime Setup Notes

### Env variable names (important)

`django-configurations` uses different env names for different settings types in this project:

- Database override: `DATABASE_URL=...`
- Profiling toggles: `DJANGO_PROFILING_ENABLED=1`
- Querycount toggle: `DJANGO_QUERYCOUNT_ENABLED=1`
- File cache location: `DJANGO_FILE_CACHE_LOCATION=/tmp/...`

Using `DJANGO_DATABASE_URL` does **not** override the DB here.

### Temp SQLite DB location under escalated commands

When profiling with escalated commands, the process did not see the same SQLite file contents created in the sandbox workspace path. The reliable approach was:

- create/migrate/load the profiling DB in `/tmp`
- run `DevConfiguration` against `/tmp/oldp-dev-profile.sqlite3`

## Methodology

### 1. Validate profiling middleware stack

- Enabled Silk + QueryCount via env vars
- Verified:
  - middleware activation
  - `/silk/` route registration
  - `X-DjangoQueryCount-*` headers on responses
  - Silk request recording in DB

### 2. Build a temporary profiling DB

Using a fresh SQLite DB for reproducible profiling:

```bash
TMPDIR=/tmp SQLITE_TMPDIR=/tmp \
DJANGO_CONFIGURATION=DevConfiguration \
DATABASE_URL=sqlite:////tmp/oldp-dev-profile.sqlite3 \
DJANGO_PROFILING_ENABLED=1 \
DJANGO_QUERYCOUNT_ENABLED=1 \
DJANGO_FILE_CACHE_LOCATION=/tmp/django_cache_devprofile \
.venv/bin/python manage.py migrate --noinput
```

Load fixture data:

```bash
TMPDIR=/tmp SQLITE_TMPDIR=/tmp \
DJANGO_CONFIGURATION=DevConfiguration \
DATABASE_URL=sqlite:////tmp/oldp-dev-profile.sqlite3 \
DJANGO_PROFILING_ENABLED=1 \
DJANGO_QUERYCOUNT_ENABLED=1 \
DJANGO_FILE_CACHE_LOCATION=/tmp/django_cache_devprofile \
.venv/bin/python manage.py loaddata \
  locations/countries.json \
  locations/states.json \
  locations/cities.json \
  courts/courts.json \
  sources/default.json \
  laws/laws.json \
  cases/cases.json
```

### 3. Run profiled local server (`DevConfiguration`)

```bash
TMPDIR=/tmp SQLITE_TMPDIR=/tmp \
DJANGO_CONFIGURATION=DevConfiguration \
DATABASE_URL=sqlite:////tmp/oldp-dev-profile.sqlite3 \
DJANGO_PROFILING_ENABLED=1 \
DJANGO_QUERYCOUNT_ENABLED=1 \
DJANGO_FILE_CACHE_LOCATION=/tmp/django_cache_devprofile \
.venv/bin/python manage.py runserver 127.0.0.1:8014 --noreload
```

### 4. Measure cold vs warm requests (2-pass)

Two sequential requests per endpoint were issued with `curl`, capturing headers and timing:

- status
- `X-DjangoQueryCount-Count`
- `Vary`
- `Cache-Control`
- `ETag`
- `time_total`

Example:

```bash
curl -sS -o /dev/null -D - -w 'time_total=%{time_total}\n' \
  http://127.0.0.1:8014/api/laws/
```

### 5. Use Silk SQL traces for root-cause analysis

For hotspots (especially `/case/foo-case`), Silk SQL traces were inspected to attribute remaining queries to:

- view code
- model methods
- template-triggered calls

## Findings

## A. `DevConfiguration` profiling (with real cache behavior)

### Endpoint results (cold -> warm)

| Endpoint | Querycount | Time |
|---|---|---|
| `/api/` | `2 -> 2` | `0.173s -> 0.043s` |
| `/api/cases/` | `6 -> 4` | `0.089s -> 0.042s` |
| `/api/laws/` | `6 -> 2` | `0.115s -> 0.066s` |
| `/api/law_books/` | `6 -> 2` | `0.070s -> 0.036s` |
| `/` | `8 -> 2` | `0.528s -> 0.044s` |
| `/case/` | `6 -> 2` | `0.109s -> 0.091s` |
| `/case/foo-case` (before case-detail follow-up optimizations) | `12 -> 8` | `0.091s -> 0.091s` |

### Interpretation

- Cache behavior is working for API and frontend pages under `DevConfiguration`.
- Cached API endpoints show the expected `Vary` headers (including `Authorization`, `Cookie`, `Accept-Language`, `Host`).
- Frontpage and case list show significant query-count reductions on warm requests.
- Case detail remained the main hotspot after the initial pass.

## B. Case Detail (`/case/foo-case`) Deep Dive and Optimizations

### Warm-request SQL (before follow-up case optimizations)

Silk showed 3 application SQL queries on warm anonymous requests:

1. public annotation markers (`item.get_markers(request)`)
2. related cases (`item.get_related()`)
3. references query (`item.get_grouped_references()` via template include)

This showed that the existing shared case cache only covered:

- case object
- reference markers

It did **not** yet cache template-driven shared data (`references`, `related_cases`) or anonymous marker/content rendering.

### Optimization 1: Cache shared references + related cases

Implemented:

- materialize and cache `item.references`
- compute/cache `related_cases`
- pass `related_cases` to template to avoid `item.get_related()` during render

Result for `/case/foo-case`:

- warm: `8 -> 4` querycount
- warm time: `~0.091s -> ~0.058s`

Silk warm SQL after this step:

- 1 application SQL query remained (public markers)

### Optimization 2: Cache anonymous public markers + rendered content

Implemented anonymous-only shared caches for:

- public markers list
- annotated rendered content (`insert_markers(...)` result)

This is safe for anonymous users because marker visibility is public-only.

#### Final `/case/foo-case` result (anonymous)

- cold: `12` querycount, `~0.613s`
- warm: `2` querycount, `~0.049s`

Silk warm SQL after this step:

- **0 application SQL queries**
- Remaining `querycount` is profiling instrumentation writes (Silk)

## C. Cache Correctness Fixes Verified During Profiling

The branch now includes cache correctness protections that were important to verify while profiling:

- API cache variance includes:
  - `Authorization`
  - `Cookie`
  - `Accept-Language`
  - `Host`
- Role-based page cache keys vary by:
  - method
  - host
  - language
  - path
  - role
- Role cache skips responses that:
  - set cookies
  - vary on cookie
  - are not cache-safe

This avoids cross-user/session and cross-locale/domain cache contamination while keeping aggressive caching enabled.

## D. Remaining Bottlenecks / Next Targets

After the case-detail follow-up optimizations:

- Warm anonymous `/case/foo-case` is effectively DB-free.
- Remaining performance work is more likely CPU/template/middleware/compression than DB on warm hits.
- Best next profiling target:
  - `/search/?q=...`
  - validate search facet cache hit behavior
  - inspect cache-miss CPU hotspots (facet processing and template rendering)

## E. Continued Profiling: Search and Law Pages (same temp DB, `DevConfiguration`)

This follow-up pass profiled:

- `/search/?q=gg`
- `/search/autocomplete?q=gg`
- `/law/gg/` (law book page)
- `/law/gg/artikel-1` (law detail page)

using the same profiling DB and the same `DevConfiguration` methodology as above, with a fresh file cache directory.

### Endpoint results (cold -> warm)

| Endpoint | Querycount | Time |
|---|---|---|
| `/search/?q=gg` | `2 -> 2` | `0.683s -> 0.042s` |
| `/search/autocomplete?q=gg` | `2 -> 4` | `0.064s -> 0.036s` |
| `/law/gg/` | `408 -> 2` | `1.615s -> 0.045s` |
| `/law/gg/artikel-1` | `22 -> 2` | `0.168s -> 0.034s` |

### Silk request metadata (application SQL focus)

`querycount` includes profiling/instrumentation overhead, so Silk request metadata and SQL traces were used to measure application SQL:

- `/search/?q=gg`
  - cold: `meta_num_queries = 1`
  - warm: `meta_num_queries = 1`
  - warm Silk SQL count: `0`
- `/search/autocomplete?q=gg`
  - cold: `meta_num_queries = 1`
  - warm: `meta_num_queries = 1`
  - warm Silk SQL count: `0`
- `/law/gg/`
  - cold: `meta_num_queries = 226`
  - warm: `meta_num_queries = 1`
  - warm Silk SQL count: `0`
- `/law/gg/artikel-1`
  - cold: `meta_num_queries = 14`
  - warm: `meta_num_queries = 1`
  - warm Silk SQL count: `0`

### Interpretation

- Search and law pages are all effectively DB-free on warm cache hits (application SQL `0` in Silk traces).
- `/search/?q=gg` shows a large cold-to-warm drop (`~683ms -> ~42ms`), which confirms the role-level page cache is paying off.
- `/law/gg/` is now the standout cold-path hotspot (very high SQL query volume before cache).

### Search profiling caveat (important)

In this local profiling environment, Elasticsearch was not reachable and the server logged connection failures for the search requests. The search views still returned `200` via the application's error-handling/fallback path.

Implication:

- the search endpoint timings above are still useful for measuring page-cache impact and local fallback rendering behavior
- they do **not** represent true indexed-search performance under a healthy Elasticsearch backend

## F. New Bottleneck Identified: Cold `/law/gg/` Page (`LawBook.sections` N+1)

### Observed pattern

Silk SQL trace for cold `/law/gg/` showed:

- `203` SQL rows recorded
- `226` application SQL queries (`meta_num_queries`)
- `198` duplicate queries of the same form:

`SELECT laws_lawbook.id, laws_lawbook.sections FROM laws_lawbook WHERE laws_lawbook.id = ... LIMIT 21`

### Root cause

This is a template-driven N+1 on the law book page:

- `oldp/apps/laws/templates/laws/book.html` loops over `items` and calls `item.get_section` (`oldp/apps/laws/templates/laws/book.html:18`, `oldp/apps/laws/templates/laws/book.html:21`)
- `Law.get_section()` calls `self.book.get_sections()` (`oldp/apps/laws/models.py:378`)
- `get_sections()` accesses `self.sections` (`oldp/apps/laws/models.py:142`)
- In `view_book`, the queryset defers `book__sections` via `Law.defer_fields_list_view` (`oldp/apps/laws/views.py:107`, `oldp/apps/laws/models.py:285`)

Because `book__sections` is deferred, each `item.get_section` call triggers a lazy refresh of `LawBook.sections`, causing repeated identical queries.

### Recommended fix (next pass)

Either of these should remove the N+1 on cold `/law/gg/`:

1. Do not defer `book__sections` in `view_book` (or in the list-view defer set used there)
2. Precompute section labels once in the view (e.g., `sections = book.get_sections()`) and use that in the template instead of `item.get_section`

## G. Smaller Cold-Path Pattern: Duplicate `get_revision_dates()` Queries on Law Pages

Both cold `/law/gg/` and `/law/gg/artikel-1` traces show duplicate revision-date queries:

- `SELECT laws_lawbook.revision_date ... WHERE code = ... ORDER BY revision_date DESC` (executed twice)

Likely cause:

- templates call `book.get_revision_dates` multiple times (iteration + length check), e.g. `laws/book.html:43` and `laws/book.html:49`
- `LawBook.get_revision_dates()` returns a queryset each time and does not cache/materialize (`oldp/apps/laws/models.py:186`)

This is a smaller issue than the `book.sections` N+1 and mostly affects cold requests, but it is still a clean optimization candidate (cache on instance or materialize once in the view).

## H. Implemented Follow-up Fix for Law Pages and Re-Profiling Results

A follow-up patch was applied to remove the template-driven duplicate method calls on law pages without undefering `book__sections` on every `Law` row.

### Implemented changes

- `view_book(...)`
  - materialize `revision_dates = list(book.get_revision_dates())` once
  - materialize `items` list once
  - compute `item.display_section` from `book.get_sections()` once in the view (avoid `item.get_section()` in template loop)
- `view_law(...)`
  - materialize `revision_dates = list(book.get_revision_dates())` once
  - materialize `related_laws = item.get_related()` once
- templates updated to use `revision_dates`, `related_laws`, and `item.display_section`

This removes:

- the `/law/gg/` cold `LawBook.sections` N+1
- duplicate `get_revision_dates()` calls in both law templates
- duplicate `item.get_related()` calls in `laws/law.html`

### Re-profiled results (same temp DB, `DevConfiguration`)

| Endpoint | Before (cold -> warm) | After (cold -> warm) |
|---|---|---|
| `/law/gg/` querycount | `408 -> 2` | `10 -> 2` |
| `/law/gg/` time | `1.615s -> 0.045s` | `0.676s -> 0.056s` |
| `/law/gg/artikel-1` querycount | `22 -> 2` | `20 -> 2` |
| `/law/gg/artikel-1` time | `0.168s -> 0.034s` | `0.154s -> 0.037s` |

### Silk application SQL (post-fix)

- `/law/gg/`
  - cold: `meta_num_queries = 5` (down from `226`)
  - warm: `meta_num_queries = 1` (profiling write only)
  - warm Silk SQL count: `0`
- `/law/gg/artikel-1`
  - cold: `meta_num_queries = 11` (down from `14`)
  - warm: `meta_num_queries = 1` (profiling write only)
  - warm Silk SQL count: `0`

### Remaining cold law-page queries after the fix

The largest law-book cold-path issue is resolved. Remaining cold queries on `/law/gg/` are now small and expected (book lookup, count check, revision dates, law list query).

On `/law/gg/artikel-1`, the remaining cold queries include:

- law + book fetches
- related laws query
- referencing cases query
- revision-date query

These are much smaller than the removed `book.sections` N+1 and mostly only matter on cache misses.

## I. Final Consolidated Post-Fix Sweep (API + Frontend + Laws + Search)

After the case-detail and law-page follow-up fixes, a final `DevConfiguration` profiling sweep was run against a fresh file-cache directory over:

- `/api/`
- `/api/cases/`
- `/api/laws/`
- `/api/law_books/`
- `/`
- `/case/`
- `/case/foo-case`
- `/law/gg/`
- `/law/gg/artikel-1`
- `/search/?q=gg`
- `/search/autocomplete?q=gg`

### Header/timing results (cold -> warm)

| Endpoint | Querycount | Time |
|---|---|---|
| `/api/` | `2 -> 2` | `0.162s -> 0.040s` |
| `/api/cases/` | `6 -> 2` | `0.080s -> 0.036s` |
| `/api/laws/` | `6 -> 2` | `0.117s -> 0.052s` |
| `/api/law_books/` | `6 -> 2` | `0.067s -> 0.039s` |
| `/` | `8 -> 2` | `0.514s -> 0.041s` |
| `/case/` | `6 -> 2` | `0.158s -> 0.045s` |
| `/case/foo-case` | `14 -> 2` | `0.118s -> 0.049s` |
| `/law/gg/` | `10 -> 2` | `0.121s -> 0.038s` |
| `/law/gg/artikel-1` | `20 -> 2` | `0.204s -> 0.035s` |
| `/search/?q=gg` | `2 -> 2` | `0.088s -> 0.046s` |
| `/search/autocomplete?q=gg` | `2 -> 4` | `0.061s -> 0.040s` |

### Silk request metadata summary (application SQL)

For the latest warm requests in this sweep:

- all endpoints above had `warm_sql_count = 0` in Silk
- `meta_num_queries = 1` for most warm endpoints (profiling instrumentation write)
- `querycount` header values > 1 on warm responses are instrumentation/middleware overhead, not app SQL

Selected cold `meta_num_queries` from this final sweep:

- `/api/cases/`: `3`
- `/api/laws/`: `3`
- `/api/law_books/`: `4`
- `/`: `5`
- `/case/`: `4`
- `/case/foo-case`: `6`
- `/law/gg/`: `6`
- `/law/gg/artikel-1`: `10`

### Practical conclusion

For the anonymous request paths profiled here, the current branch has reached a strong state:

- warm cache hits are effectively database-free across API and frontend pages tested
- remaining performance work is mostly cold-path optimization and CPU/template/render work

## J. Profiling Still Worth Doing (Not Completed in This Session)

The highest-value remaining profiling work is:

1. **Search with a real Elasticsearch backend available**
   - current local search timings reflect fallback/error-handling behavior because Elasticsearch was unreachable
   - true search miss/hit performance (including facet processing under real results) still needs validation

2. **Authenticated and staff variants**
   - cache variance/correctness has been fixed, but performance for:
     - authenticated non-staff users
     - staff users (extra annotation/marker queries and controls)
   - has not been profiled end-to-end in this session

3. **CPU profiling on warm pages**
   - DB work is mostly eliminated on warm hits
   - next likely costs: template render, marker insertion, middleware stack, compression
   - Silk Python profiler reported environment conflicts earlier (`Another profiling tool is already active`), so a dedicated CPU-profiler pass may need a cleaner runtime

## K. Phase 1 (Conservative) Implementation Update: Anonymous Search/API Speed

Implemented Django-only anonymous optimizations focused on public search endpoints and shared request patterns:

- Added dispatch caching + safe `Vary` headers to public search APIs:
  - `/api/cases/search/`
  - `/api/laws/search/`
- Hardened autocomplete cache behavior:
  - normalized query handling (trimmed input)
  - blank-query short-circuit (`{"results": []}`)
  - cache key now varies by host and language
  - cache key normalization is case-insensitive (improves hit rate for anon traffic)
- Small cold-path optimization for court case list pages:
  - `CourtCasesListView` now fetches `court` with `select_related("state")`

### Validation completed in this session

Targeted tests (mocked search backend, no Elasticsearch required):

- search API cache headers + response caching behavior
- autocomplete normalization cache hit behavior
- autocomplete blank-query short-circuit
- autocomplete cache-key host/language variance

### Validation still pending (for this phase)

- **ES-backed profiling** of `/api/cases/search/` and `/api/laws/search/` under a reachable Elasticsearch backend
  - local environment still lacks reachable ES, so only mocked/test validation was performed for the search APIs

### Test command used

```bash
source .venv/bin/activate
python manage.py test \
  oldp.apps.search.tests.test_api_cache_headers \
  oldp.apps.search.tests.test_views.MockedSearchViewsTestCase.test_autocomplete_blank_query_short_circuits \
  oldp.apps.search.tests.test_views.MockedSearchViewsTestCase.test_autocomplete_cache_key_varies_by_host_and_language \
  oldp.apps.search.tests.test_views.MockedSearchViewsTestCase.test_autocomplete_cache_normalizes_query \
  --verbosity 2
```

## L. Phase 2 (Conservative) Implementation Update: Public Docs/Autocomplete + Small View Wins

Implemented additional low-risk anonymous optimizations that do not require Elasticsearch:

- Wrapped public API schema/docs routes with `cache_per_role(settings.CACHE_TTL)`:
  - `/api/schema.json`
  - `/api/schema.yaml`
  - `/api/schema/` (Swagger UI)
  - `/api/docs/` (ReDoc)
- Wrapped courts autocomplete endpoints with `cache_per_role(settings.CACHE_TTL)`:
  - `/court/autocomplete/`
  - `/court/autocomplete/state/`
- Small cold-path query reduction:
  - `CourtCasesListView` court lookup now uses `select_related("state")`
- Homepage anonymous rendering tightened:
  - latest cases query is sliced in the view (only fetch 10 rows)
  - homepage count cache keys now vary by host/language

### Phase 2 profiling run (`DevConfiguration`, temp SQLite, no ES dependency)

Measured endpoints (cold -> warm):

| Endpoint | Querycount | Time |
|---|---|---|
| `/api/schema.json` | `2 -> 2` | `1.599s -> 0.055s` |
| `/api/schema.yaml` | `4 -> 2` | `1.564s -> 0.046s` |
| `/api/schema/` | `2 -> 2` | `0.057s -> 0.043s` |
| `/api/docs/` | `4 -> 2` | `0.046s -> 0.044s` |
| `/court/autocomplete/?q=ag` | `4 -> 2` | `0.045s -> 0.031s` |
| `/court/autocomplete/state/?q=ba` | `6 -> 2` | `0.047s -> 0.031s` |
| `/court/ag-aalen/` | `6 -> 2` | `0.427s -> 0.033s` |

### Silk application SQL summary (Phase 2 endpoints)

All warm requests above had:

- `warm_sql_count = 0` (application SQL)
- `meta_num_queries = 1` for most endpoints (profiling instrumentation write)

Selected cold `meta_num_queries`:

- `/api/schema.json`: `1`
- `/api/schema.yaml`: `1`
- `/court/autocomplete/`: `2`
- `/court/autocomplete/state/`: `3`
- `/court/ag-aalen/`: `4`

### Important header caveat for drf-yasg schema/docs

Even though internal Django caching now speeds up repeated schema/docs requests, drf-yasg responses still emit cache-preventing headers such as:

- `Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private`

Implication:

- **internal server-side caching works** (as shown by timing improvements and Silk warm SQL = 0)
- **downstream/browser caching is still effectively disabled** for these endpoints

If desired later, a follow-up can adjust schema/docs response headers explicitly (carefully) to enable browser/proxy caching.

## Caveats

- `django-querycount` numbers include profiling middleware/instrumentation overhead (especially Silk writes), so warm cached requests will not necessarily show `0`.
- Timing is local development timing (SQLite + dev server), useful for relative comparisons and regression detection, not production latency estimates.

## Files Changed During This Profiling Work (Relevant to Findings)

- `oldp/settings.py` (profiling/querycount runtime activation + querycount config keys)
- `oldp/utils/cache_per_user.py` (cache correctness + variance)
- `oldp/apps/search/views.py` (facet caching)
- `oldp/apps/laws/api_views.py` (`LawBookViewSet.defer(...)`)
- `oldp/apps/cases/api_views.py` (API cache vary headers)
- `oldp/api/views.py` (API cache vary headers)
- `oldp/apps/cases/views.py` (case detail caching improvements)
- `oldp/apps/cases/templates/cases/case.html` (avoid template-triggered related query)
