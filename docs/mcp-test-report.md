# OLDP MCP Server — Test Report

A user-driven test of the [OLDP MCP server](mcp.md). This document records observations,
bugs and suggested improvements identified during a realistic German legal-research
session that exercised every tool exposed by the server.

- **Date:** 2026-05-06
- **Endpoint under test:** `https://de.openlegaldata.io` (per `get_platform_info`)
- **Reported coverage:** 419,984 cases / 1,119 courts / 113,494 law sections / 6,935,986 references
- **Tools exercised:** all 14 (`get_platform_info`, `get_server_instructions`,
  `list_courts`, `get_court`, `list_law_books`, `get_law_section`, `search_cases`,
  `search_laws`, `filter_cases`, `get_case`, `get_case_references`,
  `get_citing_cases`, `get_cases_for_law`, `validate_citation`, `get_case_statistics`)

## Test scenarios

The MCP server was tested by carrying out tasks a German legal researcher would
realistically run:

1. Look up the Bundesgerichtshof and core statutes (§ 823 BGB, § 32 StGB, § 556d BGB).
2. Search for case law on two topical issues: the diesel emissions scandal
   ("Volkswagen Abgasmanipulation") and rent control ("Mietpreisbremse").
3. Retrieve a full OLG Stuttgart ruling (12 U 64/17, case id 183007) on dealer
   liability in the diesel scandal.
4. Walk the citation graph forward (case → laws/cases) and backward
   (cited case → citing cases), and find cases interpreting § 823 BGB.
5. Validate citations of all three forms (Aktenzeichen, ECLI, paragraph).
6. Aggregate statistics for the BGH and for the labor-law jurisdiction.

## What works well

- **Discovery tools** (`get_platform_info`, `list_courts`, `list_law_books`,
  `get_court`, `get_law_section`) are fast and well-shaped. `get_court(code="BGH")`
  returned full address/contact metadata and a case count of 20,308.
- **`search_cases`** delivers strong full-text Elasticsearch results with
  highlighted snippets and useful facets (court, decision type, level of appeal).
  Sample queries: "Volkswagen Abgasmanipulation" → 35 hits;
  "Mietpreisbremse" → 132 hits.
- **`get_case`** returned the full text of OLG Stuttgart 12 U 64/17 with no
  truncation; HTML-rich content (Tenor, Gründe, paragraph numbering) was preserved
  intact.
- **`filter_cases`** correctly handled exact lookups by `file_number`, `ecli`,
  and `court_slug + date_after + date_before + decision_type`. 55 BGH Urteile
  in January 2023 returned cleanly.
- **`get_case_statistics`** by `court_id` produced a clean monthly time series
  for the BGH (3,661 cases over 2022–2023) plus a `top_courts` breakdown.
- **`get_citing_cases`** correctly returned the OLG Köln decision citing
  LG Köln 24 O 216/16.

## Issues

Issues are grouped by priority for the maintainer. The criterion is impact on
correctness from the user's perspective: top-priority items return wrong data
or block usage entirely, mid-priority items are functional gaps with awkward
workarounds, low-priority items are data-quality artefacts.

| # | Title | Priority |
|---|-------|----------|
| 1 | `search_laws` returns case results when no `book_code` is given | **Top** |
| 3 | `get_cases_for_law` resolves `book_code + section` to the wrong revision | **Top** |
| 4 | `validate_citation` substring-matches too loosely | **Top** |
| 5 | `validate_citation` times out on invalid input | **Top** |
| 2 | `search_laws` does not index section titles | Mid |
| 6 | Case reference extraction is highly variable | Mid |
| 7 | `jurisdiction` / `level_of_appeal` schema documents English values, but DB stores German | Mid |
| 8 | Future-dated case records pollute results | Mid |
| 9 | Some cases are missing ECLI identifiers | Low |

## Top priority

These return wrong data or block normal usage. Fixing them removes silent
failure modes that an LLM caller will not catch.

### 1. `search_laws` returns case results when no `book_code` is given

Queries without a `book_code` filter return objects that look like cases, not law
sections. Example: `search_laws(query="Mietpreisbremse")` returns five entries
where `book_code` is `null`, `title` is "Urteil vom Landgericht Berlin …", and
`slug` is e.g. `lg-berlin-2023-02-14-63-s-12522`.

**Reproduce**

```python
search_laws(query="Mietpreisbremse")
search_laws(query="Notwehr")
```

**Expected:** law sections (or an empty result set if none match).
**Actual:** case results with case-shaped fields.

**Suggested fix:** route the query to the law-sections index regardless of
`book_code` presence; if no matches, return an empty list rather than falling
back to a different index.

### 3. `get_cases_for_law` resolves `book_code + section` to the wrong revision

The resolver behind `get_cases_for_law(book_code, section)` does not point at
the law revision used by the citation graph.

**Reproduce**

```python
get_law_section(book_code="BGB", section="823")
# → id 129924 (latest revision)

get_cases_for_law(book_code="BGB", section="823")
# → {"error": "Law section not found for book='BGB', section='823'."}

# References extracted from a case point at id 65477:
get_case_references(case_id=96538)
# → law_references[…].id = 65477 for "§ 823 BGB"

get_cases_for_law(law_id=65477)
# → 5,121 citing cases
```

So `get_law_section` and `get_cases_for_law` resolve the same human-readable
identifier (`BGB § 823`) to different rows, and the citation graph is built
against the *older* row. The same problem reproduces for `(StGB, 32)`.

**Suggested fix:** make `get_cases_for_law` aggregate over all revisions of the
section (by `book_code + section`), or document `law_id` as the only
canonical input for this endpoint and have it accept the latest revision id
transparently.

### 4. `validate_citation` substring-matches too loosely

```python
validate_citation("§ 823 BGB")
# → § 823 (correct) AND § 1823 "Vertretungsmacht des Betreuers" (false positive)

validate_citation("§ 32 StGB")
# → § 32, § 132, § 132a, § 232, § 232a (only § 32 is correct)
```

Returning § 1823 for "§ 823" is misleading — a downstream agent that trusts
`found: true` will treat the query as ambiguous when it is not.

**Suggested fix:** anchor section matching on the full normalized identifier
(e.g. `^§ 823$`), and rank exact matches first. Optionally return a
`match_type` field (`"exact"` vs. `"prefix"`) so callers can decide.

### 5. `validate_citation` times out on invalid input

```python
validate_citation("XYZ 999/99")  # raises "The operation timed out."
```

Invalid file numbers should return `{"found": false, "matches": []}` quickly,
not exhaust the timeout.

**Suggested fix:** when the citation does not match the regex for any known
citation type (`auto`-mode), short-circuit and return `not found` without a
database lookup.

## Mid priority

These return correct data on the happy path but have functional gaps,
discoverability problems, or data-quality issues that propagate into results.
A patient user can work around them; an LLM agent often cannot.

### 2. `search_laws` does not index section titles

`search_laws(query="Notwehr", book_code="StGB")` returned 0 results, but
`get_law_section(book_code="StGB", section="32")` returns a section whose
`title` field is exactly "Notwehr". Section titles appear to be excluded from
the search corpus.

**Suggested fix:** include `title` (and `kurzue` / `amtabk` if used) in the
analyzed fields of the law-section index, weighted higher than body text.

### 6. Case reference extraction is highly variable

```python
get_case_references(case_id=183007)
# → 0 law references, 0 case references
```

The case text of OLG Stuttgart 12 U 64/17 explicitly cites
§§ 123, 280, 281, 437, 812, 823, 826, 278, 433 BGB and several
BGH / OLG decisions (e.g. *BGH NJW 1990,1661*, *OLG Celle MDR 2016, 1016*).
None of these were extracted.

By comparison, `get_case_references(case_id=96538)` returned 13 law references
correctly, so the extractor works in principle — it appears to fail on certain
HTML / formatting patterns.

**Suggested fix:** investigate which formatting variant in case 183007 breaks
the extractor (HTML tables with `<rd nr="…"/>` paragraph markers; semicolon-
separated cite lists). Add regression cases. The user-facing `note` warning is
helpful, but a 100% miss rate on a heavily-cited decision is a meaningful gap.

### 7. `jurisdiction` / `level_of_appeal` schema documents English values, but DB stores German

```python
get_case_statistics(jurisdiction="labor", …)        # → 0 results
list_courts(jurisdiction="labor")                    # → 0 results

get_case_statistics(jurisdiction="Arbeitsgerichtsbarkeit", …)
# → 2,285 cases, top court Bundesarbeitsgericht (307)
```

The tool docstrings advertise `"ordinary"`, `"administrative"`, `"labor"`,
`"social"`, `"fiscal"` and `"local"` / `"regional"` / `"high"` / `"federal"`,
but the underlying field stores German values such as
`"Arbeitsgerichtsbarkeit"`, `"Ordentliche Gerichtsbarkeit"`, `"Bundesgericht"`.

**Suggested fix:** either (a) accept both English and German values and
translate at the API layer, or (b) update the schema / docstrings to document
the German values that actually work. Option (a) is friendlier to non-German-
speaking MCP clients.

### 8. Future-dated case records pollute results

```python
get_platform_info()
# → case_date_range.latest = "2029-11-13"

get_cases_for_law(law_id=65477)
# → results include dates 2027-04-06, 2026-03-31, 2026-03-31, …
```

These appear to be date-extraction errors during ingestion. They propagate
into statistics, sort orders and citation walks, and a researcher who orders
by `-date` will see fictitious "newest" decisions first.

**Suggested fix:** cap ingested dates at `today + small grace period` (e.g.
14 days for embargoed publications) and flag everything beyond that for
re-extraction.

## Low priority

A coverage / hygiene issue rather than a defect — worth tracking but not
urgent.

### 9. Some cases are missing ECLI identifiers

OLG Stuttgart 12 U 64/17 (id 183007) has `ecli: ""`. ECLI is the canonical
machine-readable identifier — agents that rely on it for deduplication or
cross-database lookup will fail silently. A coverage report (% of cases with
ECLI by court) would help prioritize backfill.

## Suggested improvements (non-bug)

- **Document the data anomalies** in `get_platform_info` itself — e.g.
  return a `data_quality` block listing known caveats (future-dated rows,
  partial reference extraction, ECLI coverage). MCP clients can then surface
  these to the LLM as ground truth.
- **Add a `revisions` parameter** to `get_law_section` so callers can request
  the historical revision active at a given date. This would make
  `get_cases_for_law` consistent and unblock historical-impact research.
- **Return `match_type`** from `validate_citation` (`"exact"`, `"prefix"`,
  `"fuzzy"`) so agents can distinguish confident hits from substring matches.
- **Expose extraction confidence** on `get_case_references` (e.g. a per-case
  `extraction_quality` score derived from text-vs-references heuristics).
  Consumers could then avoid making strong claims about cases that look
  under-extracted.
- **Server instructions could nudge users towards `filter_cases`** when they
  have an exact `file_number` / `ecli` — currently the natural reach is
  `search_cases`, which is fuzzier and slower.
- **Document the German enum values for `jurisdiction` and `level_of_appeal`**
  in `get_platform_info` (as `available_filters`) so they can be discovered
  without reading the source.

## Reproduction environment

- MCP server: OLDP MCP (whatever revision was deployed at `de.openlegaldata.io`
  on 2026-05-06).
- Client: Claude Code (Opus 4.7, 1M context).
- All tools called via the standard MCP transport — no direct database access.
