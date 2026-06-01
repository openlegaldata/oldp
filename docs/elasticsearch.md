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
- `update_index cases` — ~15-30 min for ~423k cases.

Before the reindex completes, downstream surfaces that rely on the
new field render their empty state ("No cases cite this section
yet." / "No other cases cite this decision yet." in the web UI;
empty paginated list in REST; `total_citing_cases: 0` in MCP). Free-
text search, facets, and the search backend's existing fields are
unaffected — the reindex is additive and incremental.

For the user-facing search surfaces (web `/search/`, REST
`/api/cases/search/`, MCP `search_cases`) and the full matrix of
filters they support — keyword + facets + date range + citation graph,
plus the `order_by=date` sort toggle — see [Search](searching.md).

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
