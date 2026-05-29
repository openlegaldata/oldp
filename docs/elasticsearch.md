# Elasticsearch

As search backend we rely on [Elasticsearch](http://elastic.co/). In this document we collect useful commands or queries
to work with ES.

### Propagate database entries to search index

- Rebuild index: `./manage.py rebuild_index`
- Update existing index: `./manage.py update_index`

### Index fields driving citation lookups

Three multi-value fields back the "find documents tagged with X"
filter queries. Each lives on the corresponding search index and
needs a reindex of that app whenever the field shape changes:

| Field | Index | Purpose |
|-------|-------|---------|
| `is_latest` | `LawIndex` | Boolean mirroring `LawBook.latest`. The search backend always filters `not (django_ct=laws.law AND is_latest=false)` so stale revisions never enter the haystack hydration loop. |
| `cited_laws` | `CaseIndex` | List of `"<book_slug>__<section_slug>"` tokens for every law section the case cites. Powers `/search/?cited_law_book=&cited_law_section=`, the citing-cases panel on `/law/<book>/<sec>/`, and the REST + MCP `citing_cases` endpoints. |
| `cited_cases` | `CaseIndex` | List of Case PKs (as strings) for every case the case cites. Powers `/search/?cited_case=<id>`, the citing-cases panel on `/case/<slug>/`, and the corresponding API + MCP endpoints. |

The token format used by `cited_laws` is intentional: two underscores
cannot appear inside a Django slug, so `f"{book_slug}__{section_slug}"`
is unambiguously parseable and safe to use inside an ES `query_string`
literal. Helper `oldp.apps.cases.search_indexes.cited_law_token`
renders the token; consumers should call it rather than concatenating
manually.

### Reindex requirement after deploy

A release that adds or changes one of the fields above needs an
operator-run reindex on prod to populate the new shape. From inside
the app container:

    python manage.py update_index laws   # populates is_latest
    python manage.py update_index cases  # populates cited_laws + cited_cases

Estimated runtime (May 2026 prod data):

- `update_index laws` — ~4-5 min for ~110k law sections.
- `update_index cases` — ~28 h single-worker, ~12.5 h with `-k 4`
  for ~424k cases. Pass `-k 4` on prod to keep the wall time
  manageable; the bottleneck is the ~1 MB `content` TextField pulled
  per row, and parallel workers amortise the per-batch network cost
  across 4 MySQL→app sockets.

Before the reindex completes, downstream surfaces that rely on the
new field render their empty state ("No cases cite this section
yet." / "No other cases cite this decision yet." in the web UI;
empty paginated list in REST; `total_citing_cases: 0` in MCP). Free-
text search, facets, and the search backend's existing fields are
unaffected — the reindex is additive and incremental.

### Realtime sync on Case writes

`oldp.apps.cases.signals` connects `post_save` and `post_delete`
handlers on `Case` that mirror the row-level `review_status` filter
from `CaseIndex.index_queryset` into the ES index in realtime:

| Event | ES action |
|-------|-----------|
| `Case.save()` with `review_status='accepted'`        | `index.update_object()` (upsert) |
| `Case.save()` with `review_status` in `{pending,rejected}` | `index.remove_object()` |
| `Case.delete()` (hard delete)                        | `index.remove_object()` |
| `loaddata` (`raw=True` on the save signal)           | no-op — fixture flow runs `update_index` after |

Both handlers defer via `transaction.on_commit`, so a rolled-back
save never leaks into ES, and ES exceptions are logged but swallowed
so a search-backend outage cannot break `Case.save()` callers. This
covers admin edits and the case PATCH API endpoint; the only
remaining drift source is `QuerySet.update()` (see below).

### Bulk operations bypass the signals

`Case.objects.filter(...).update(...)` is a single SQL `UPDATE` that
**does not fire `post_save`**, so the realtime sync above does not
run for bulk paths. `bulk_approve_cases` is the canonical example:

    # Approve without updating ES — fast, but ES will drift
    python manage.py bulk_approve_cases

    # Approve and immediately sync the touched rows into ES
    python manage.py bulk_approve_cases --update-index

Always pass `--update-index` when running `bulk_approve_cases` on
prod unless you plan to run a full `update_index cases` afterwards.
The flag batches the updated PKs through `backend.update(index,
cases)` in the same batch boundaries used by the SQL update, so
there is no separate full-table scan.

### Periodic reconciliation

For periodic safety (e.g., after manual SQL edits or to catch any
row that slipped through a bulk path) run the drift-prune script
from the deployment repo:

    deployment/scripts/prune_stale_es_docs.sh cases.case            # dry run
    deployment/scripts/prune_stale_es_docs.sh cases.case --apply    # delete stale docs

The script scrolls every `cases.case` doc PK from ES, diffs against
the canonical `Case.get_queryset().values_list("pk")` set, and
deletes only the orphans. Runs in seconds even on the full 424k
index because it transfers only PKs, not document payloads.

### Service-layer surfaces backed by Elasticsearch

After PR #224 / PR #225 the citation graph is served by ES on every
surface except the `references/` forward-refs endpoints (which return
the immediate marker chain — a Python dict — and have always come
straight out of the ORM):

| Surface | Backend |
|---------|---------|
| Web `/law/<book>/<sec>/` "Referenced by" panel | ES (`cited_laws`) |
| Web `/case/<slug>/` "Cited by" panel | ES (`cited_cases`) |
| Web `/search/?cited_law_book=&cited_law_section=` | ES (`cited_laws`) |
| Web `/search/?cited_case=<id>` | ES (`cited_cases`) |
| REST `/api/laws/<id>/citing_cases/` | ES (`cited_laws`) |
| REST `/api/cases/<id>/citing_cases/` | ES (`cited_cases`) |
| REST `/api/{laws,cases}/<id>/references/` | SQL (forward refs) |
| REST `/api/references/` flat resource | SQL (analytical) |
| REST `/api/{laws,cases}/<id>/citing_laws/` | SQL (rare) |
| MCP `get_cases_for_law` | ES (`cited_laws`) |
| MCP `get_citing_cases` (cases citing a case) | ES (`cited_cases`) |
| MCP `get_case_references` (forward refs) | SQL |

ES outage on a citing-cases surface returns:

- Web: a "search unavailable" notice with a deep link to the search
  results page (the user can retry once ES recovers).
- REST: 503 `SearchBackendUnavailable` (hard outage) or 503
  `SearchBackendTimeout` (`retryable: true` in the body — transient
  warm-up).
- MCP: `{error, retryable, hint}` envelope matching the
  `search_cases` tool's contract.

The relational citation graph (`Reference` rows + marker
through-tables) remains the source of truth and feeds the ES
indexer — see `oldp/apps/references/services/citation_graph.py`.


### Queries

```
curl -XGET localhost:9200/oldp/law/_search?pretty&query=

curl -XGET localhost:9200/oldp/law_search?pretty -d '
{
    "query": {
        "match" : {
            "book_code" : "AbwV"
        }
    },
    "sort": [
        { "doknr": { "order": "asc" } },
        "_score"
    ],
    "_source" : ["doknr", "title"]
}'

curl -XGET localhost:9200/oldp/case/_search?pretty -d '
{
    "_source" : ["text", "title"]
}'

```


#### Check cluster health

```bash
curl -XGET https://localhost:9200/_cat/health?v
```

### Load Index Mappings
```
curl -XPUT localhost:9200/leegle -d @oldp/assets/es_index.json
```
