# Search

OLDP exposes the same Elasticsearch-backed search engine on three surfaces:

| Surface | Endpoint | Use case |
|---------|----------|----------|
| Web UI | `/search/` | Human browsing with facets, citation chip, pagination |
| REST | `/api/cases/search/`, `/api/laws/search/` | Programmatic full-text queries |
| MCP | `search_cases`, `search_laws`, `search_legal`, `get_similar_cases` tools | Agent-driven research |

All three share the same backend (`CaseIndex` / `LawIndex` in
`oldp/apps/cases/search_indexes.py` and `oldp/apps/laws/search_indexes.py`)
and the same `SearchQueryBuilder` (`oldp/apps/search/api.py`), so a result
that matches in one surface also matches in the others — subject to each
surface's input contract.

## Query syntax

The keyword query (`q` / `text` / `query`) is parsed as Elasticsearch
[`query_string`](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html)
syntax on every surface. Supported operators:

| Feature | Example | Notes |
|---------|---------|-------|
| Implicit AND | `eigenbedarf kündigung` | All bare terms must match (default operator is AND). |
| Exact phrase | `"berechtigtes Interesse"` | Terms must appear adjacent, in order. Typographic quotes are normalized — pasting `„…"` or `»…«` from a PDF/Word works the same as ASCII `"…"`. |
| Exclude | `kündigung -strafrecht` | Drops documents containing the excluded term (`-` or `NOT`). |
| OR | `urteil OR beschluss` | **Case-sensitive** — lowercase `or` is treated as a literal term, not an operator. Same for `AND`, `NOT`. |
| Required | `+eigenbedarf kündigung` | Mostly redundant given the AND default. |
| Grouping | `(urteil OR beschluss) AND mietrecht` | Parentheses group sub-expressions. |
| Wildcard | `mietr*`, `m?etrecht` | `*` = any chars, `?` = one char. |
| Fuzzy | `vertrag~` | Edit-distance match for typos. |
| Field-scoped | `title:Mietrecht` | Restricts a clause to one field. Footgun: `title:foo bar` scopes only `foo`. |

Malformed fragments (a stray quote, unbalanced parens) are sanitized
before they reach Elasticsearch, so they degrade gracefully instead of
erroring.

### German language handling

Free-text fields use a German analyzer (`german_legal`: light stemming +
`german_normalization` + a legal synonym filter), so queries match across
morphology and common variants automatically — no special syntax needed:

- **Inflection / plurals**: `Vertrag` matches `Verträge`, `Frist` matches
  `Fristen`.
- **Umlaut / ß normalization**: `Massnahme` matches `Maßnahme`, `Strasse`
  matches `Straße`.
- **Gendered roles** (synonyms): `Vermieter` matches `Vermieterin`,
  `Kläger` matches `Klägerin`.
- **Spelling variants** (synonyms): `Schadenersatz` matches
  `Schadensersatz` (Fugen-s).

Stemming is intentionally *light* (legal precision over recall): distinct
lemmas are kept apart, e.g. `Kündigung` (termination) does **not** collapse
into `kundig` (knowledgeable). There is no stopword removal, so function
words inside an exact phrase (`"Treu und Glauben"`) still line up.

> Changing the analyzer requires a full reindex — see
> [Elasticsearch](elasticsearch.md) and the deployment runbook.

## Available filters

Every filter composes with every other filter (logical AND).

| Filter | Web param | REST param | MCP kwarg (`search_cases`) | Notes |
|--------|-----------|------------|----------------------------|-------|
| Keyword query | `q` | `text` | `query` | Lucene syntax supported on all surfaces. REST requires this; web/MCP allow empty if other filters are set. |
| Date range | `start_date`, `end_date` | `start_date`, `end_date` | `start_date`, `end_date` | `YYYY-MM-DD`, inclusive on both ends. Bad strings are logged and silently dropped. |
| Court | `selected_facets=court_exact:<code>` | — (use `filter_cases` ORM tool for REST/MCP court filter) | `court_code` | Exact match on the court code (e.g. `BGH`). |
| Decision type | `selected_facets=decision_type_exact:<type>` | — | `decision_type` | Exact, e.g. `Urteil`, `Beschluss`. |
| Cited law section | `cited_law_book` + `cited_law_section` | `cited_law_book` + `cited_law_section` | `cited_law_book` + `cited_law_section` | Both required together. Case-only — silently ignored on `/api/laws/search/`. |
| Cited case id | `cited_case=<int>` | `cited_case=<int>` | `cited_case_id` | Mutually exclusive with the law-citation pair (law citation wins when both are sent). |
| Sort | `order_by=relevance\|date\|most_cited` | — | `sort=relevance\|date\|most_cited` (`search_cases`) | `date` = newest first; `most_cited` = most-cited (landmark) first; default is ES relevance score. |

### Combined filters

Citation filters compose with keyword + facets + date range. The form does
not pick one filter at the cost of another — every filter narrows the
result set independently.

```
# Cases citing § 823 BGB that mention "Mietrecht"
/search/?q=Mietrecht&cited_law_book=bgb&cited_law_section=823

# Same, restricted to BGH and 2020
/search/?q=Mietrecht&selected_facets=court_exact:BGH
       &start_date=2020-01-01&end_date=2020-12-31
       &cited_law_book=bgb&cited_law_section=823

# Newest cases first
/search/?q=Mietrecht&order_by=date
```

The citation chip in the web UI shows the active citation filter with a
clear (×) link that removes only the citation params and keeps `q` /
facets intact. The "Sort by" group in the sidebar auto-submits on
change. Clicking a year tile under the publication-date facet preserves
the citation chip, every selected facet, and the current sort.

### Sort order

`order_by=date` orders by case publication date, newest first.
`order_by=most_cited` orders by reverse-citation count
(`citing_cases_count`) — how often a decision is cited by other cases —
surfacing landmark precedent first. Empty value (or any other value)
leaves Elasticsearch's relevance score ordering. The results-count label
tells you which order is active:

```
192 documents sorted by date.
4 citing cases, sorted by date.
```

The German UI renders the equivalent: *"192 Dokumente sortiert nach
Datum."* / *"4 zitierende Entscheidungen, sortiert nach Datum."*

## REST examples

```bash
# Keyword + cited law section
curl -G "https://de.openlegaldata.io/api/cases/search/" \
  --data-urlencode "text=Mietrecht" \
  --data-urlencode "cited_law_book=bgb" \
  --data-urlencode "cited_law_section=823" \
  -H "Authorization: Token $OLDP_API_TOKEN"

# Keyword + date range
curl -G "https://de.openlegaldata.io/api/cases/search/" \
  --data-urlencode "text=Urheberrecht" \
  --data-urlencode "start_date=2023-01-01" \
  --data-urlencode "end_date=2023-12-31" \
  -H "Authorization: Token $OLDP_API_TOKEN"

# Cases citing a specific case (citation-graph filter)
curl -G "https://de.openlegaldata.io/api/cases/search/" \
  --data-urlencode "text=Schadensersatz" \
  --data-urlencode "cited_case=12345" \
  -H "Authorization: Token $OLDP_API_TOKEN"
```

The REST contract requires the `text` param (returns 400 otherwise).
Citation params alone aren't accepted on the REST surface — use the
dedicated nested actions (`/api/laws/<id>/citing_cases/`,
`/api/cases/<id>/citing_cases/`) for "all citing cases" without keyword
refinement. See [API overview — Citations & Cross-References](api/api-overview.md#citations--cross-references)
for those endpoints.

## MCP examples

```python
# All citing cases of § 823 BGB, paginated — no keyword
get_cases_for_law(book_code="BGB", section="823", limit=20)

# Same set, narrowed by keyword + court (combined search)
search_cases(query="Mietrecht", court_code="BGH",
             cited_law_book="bgb", cited_law_section="823", limit=10)

# Cases citing a specific case (reverse citation) narrowed by keyword
search_cases(query="Vermieterpflichten", cited_case_id=12345, limit=10)

# Date-range only with citation graph
search_cases(query="", start_date="2023-01-01", end_date="2023-12-31",
             cited_law_book="bgb", cited_law_section="823")
```

For "give me every citing case" without keyword refinement, prefer the
dedicated `get_cases_for_law` / `get_citing_cases` tools — `search_cases`
exists for combined searches that intersect citations with keyword,
court, or date.

### Unified and similarity search (MCP)

```python
# One call across BOTH legislation and case law, grouped by type.
# Use when you don't know whether the answer is statute or jurisprudence.
search_legal(query="Eigenbedarf", limit=5)
# -> {"laws": [...], "cases": [...], "total_laws": N, "total_cases": M}

# Find cases textually similar to a known on-point decision (more_like_this).
get_similar_cases(case_id=12345, limit=10)
```

`search_legal` returns results **grouped** by type rather than as one
merged ranked list: court decisions are long and out-score short statute
texts on relevance, so a merged top-N would return only cases and bury the
on-point law. For type-specific control (citation/court/date filters), use
`search_cases` / `search_laws` directly.

When a `book_code` (e.g. for `get_cases_for_law`) or a court `code`/`slug`
(for `get_court`) is not found, the error carries a `suggestions` list of
the closest existing codes (a `did_you_mean` hint), e.g.
`"DSGVOO"` → `["DSGVO", …]`.

## Surface differences at a glance

|  | Web | REST | MCP |
|--|-----|------|-----|
| Keyword required? | No (any other filter unlocks the query) | Yes (`text` returns 400 if missing) | No |
| Facet selection | `selected_facets` | Use `filter_cases` for ORM filters | Built-in kwargs |
| Sort order | `order_by` toggle | — (relevance only) | — (relevance only) |
| Citation params | Optional | Optional | Optional |
| Highlighting | Inline in result list | `snippets` field with `<em>` tags | `snippets` array |
| Pagination | Standard | `limit` + `offset` | `limit` only (≤50) |

## Backend details

Citation lookups use multi-value fields on `CaseIndex`:

- `cited_laws` — list of `"<book_slug>__<section_slug>"` tokens
- `cited_cases` — list of cited-case PKs (as strings)

Built via `oldp.apps.cases.search_indexes.cited_law_token(book, section)`;
consumers should call this helper rather than concatenating the token
manually. The slug pair is stable across book revisions, so citation
queries survive book-revision turnover.

`most_cited` sorting uses a denormalized `Case.citing_cases_count` (number
of distinct accepted cases citing a decision), mirrored into the
`CaseIndex.citing_cases_count` ES field. It is **approximate between
recompute runs**: recompute it off the hot path with
`manage.py update_citing_counts` (a single grouped aggregate, ~90s) after
an ingestion + reference-extraction pass, then reindex to mirror the new
counts into Elasticsearch.

For the underlying index fields, the operator-run reindex command, and
the ES outage behaviour on each surface, see
[Elasticsearch](elasticsearch.md). For the citation-graph endpoints
(REST `/api/{cases,laws}/<id>/citing_*/` and the flat `/api/references/`),
see [API overview — Citations & Cross-References](api/api-overview.md#citations--cross-references).
