# OLDP MCP Server

The Open Legal Data Platform exposes a [Model Context Protocol (MCP)](https://spec.modelcontextprotocol.io/) server, enabling AI agents (Claude, Cursor, etc.) to search, retrieve, and navigate German legal data including court decisions and legislation with cross-references.

## Quick Start

### Claude Desktop / Claude Code

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "oldp": {
      "url": "https://de.openlegaldata.io/mcp"
    }
  }
}
```

### Claude.ai (Custom Connector)

1. Go to **Settings → Connectors → Add Custom Connector**
2. Enter URL: `https://de.openlegaldata.io/mcp`
3. Click **Add** — works immediately without login

### Claude Code CLI

```bash
claude mcp add --transport http oldp https://de.openlegaldata.io/mcp
```

## Authentication

The MCP server supports two modes:

| Mode | How it works | Rate limit |
|------|-------------|------------|
| **Anonymous** | No login required | 500 requests/hour (shared for Anthropic IPs) |
| **Authenticated** | OAuth 2.0 login with OLDP account (or API token) | Same per-user budget as the REST API (5,000 requests/hour by default), shared across REST API and MCP |

Authenticated MCP requests and REST API requests draw from one per-user quota: every HTTP request to either surface counts against it, custom per-token limits and the profile-completion bonus apply to both, and the account dashboard shows the combined usage.

### OAuth Flow

The server implements OAuth 2.0 with PKCE and Dynamic Client Registration (RFC 7591). Discovery endpoints:

- `/.well-known/oauth-protected-resource` — Resource metadata
- `/.well-known/oauth-authorization-server` — Authorization server metadata
- `/oauth/register/` — Dynamic Client Registration
- `/oauth/authorize/` — Authorization endpoint
- `/oauth/token/` — Token endpoint

The consent screen shown at `/oauth/authorize/` overrides django-oauth-toolkit's default template with `oldp/assets/templates/oauth2_provider/authorize.html` (OLDP micro layout, styles in `scss/oldp/_oauth.scss`). The template lives in the project template dir rather than the `mcp` app because `oauth2_provider` precedes `oldp.apps.mcp` in `INSTALLED_APPS`, so an app-level override would be shadowed.

## Available Tools

### Discovery

| Tool | Description |
|------|------------|
| `get_platform_info` | Platform coverage summary: total cases, laws, courts, date ranges |
| `list_courts` | Browse/filter courts by type, state, jurisdiction, level of appeal |
| `list_law_books` | List available law books (BGB, StGB, GG, etc.) with section counts |

### Search

| Tool | Description |
|------|------------|
| `search_legal` | Unified search across BOTH laws and cases in one call, grouped by type (`laws` + `cases`). Use when a question may be answered by statute or case law. Grouped, not merged — long case bodies would otherwise out-score and bury the on-point law |
| `search_cases` | Full-text search via Elasticsearch. Returns snippets, not full text. Accepts citation-graph filters (`cited_law_book` + `cited_law_section` or `cited_case_id`) that compose with the keyword query — e.g. "cases citing § 823 BGB that mention 'Mietrecht'". `sort=relevance\|date\|most_cited` (most_cited = landmark precedent); each result carries `citing_cases_count` and (relevance sort) `match_quality` (high/medium/low) |
| `search_laws` | Full-text search across law sections. Returns snippets only |
| `get_similar_cases` | Cases textually similar to a given case (Elasticsearch `more_like_this`). For comparative research from one on-point decision |
| `filter_cases` | Structured ORM filtering by court, date, file number, ECLI, etc. |

See [Search](searching.md) for the full filter matrix and combined-search
examples across all three surfaces.

### Retrieval

| Tool | Description |
|------|------------|
| `get_case` | Full case by ID/slug: metadata plus complete (untruncated) plain-text `content`. Optional `offset`/`length` return a snippet instead (see below) |
| `get_law_section` | Law text by book code + section (e.g. "BGB" + "823"), complete plain-text `content`. Supports the same `offset`/`length` snippet mode |
| `get_court` | Detailed court info: name, address, contact, case count |

#### Text format

`get_case` and `get_law_section` return the document text as **plain text,
not HTML** (the REST API keeps serving the stored HTML). It is derived the
same way as the text in the search index — tags stripped, HTML entities
decoded (`&#228;` → `ä`), reference markers removed — and then normalized
so it is compact and readable:

- line breaks and indentation in the HTML source count as spaces;
- block elements (paragraphs, headings, list items, …) end a line and empty
  lines are dropped, so every paragraph is one line;
- lists start on a new line and a list number or Randnummer stays on the
  line of its item (`1. Einkünfte aus …`, `12 Die Revision ist …`);
- sentence numbers (`<sup>`) are separated from the following word
  (`(1) 1 Der Einkommensteuer unterliegen`).

Markup-heavy decisions are therefore much shorter than their HTML (e.g. BGH
VII ZR 105/18: 48,596 characters of HTML, 27,081 of text).

#### Reading long texts in snippets (`offset` / `length`)

The tools never truncate: with default arguments `content` holds the whole
text. Long decisions can exceed an agent's context budget, so both tools
accept two optional integer parameters to read the text piece by piece:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `offset` | `0` | Start position, in characters of the plain text described above |
| `length` | `0` | Number of characters to return; `0` = until the end |

Positions always refer to the plain text (identical to the full `content`),
never to the raw HTML.

As soon as `offset` or `length` is non-zero, the response omits `content`
and contains a `snippet` object next to the usual metadata:

```json
{
  "id": 318054,
  "file_number": "VII ZR 105/18",
  "...": "...",
  "snippet": {
    "text": "Tenor\nAuf die Revision des Beklagten ...",
    "offset": 0,
    "length": 10000,
    "total_length": 27081,
    "has_more": true,
    "next_offset": 10000
  }
}
```

| Field | Meaning |
|-------|---------|
| `text` | The requested plain-text slice |
| `offset` | Start position of `text` |
| `length` | Actual length of `text` (shorter than requested at the end) |
| `total_length` | Length of the whole plain text — use it to plan how many calls are needed |
| `has_more` | `true` if text remains after this slice |
| `next_offset` | Pass as `offset` in the next call; `null` when `has_more` is `false` |

To read a whole decision in chunks:

1. `get_case(case_id=318054, length=10000)`
2. `get_case(case_id=318054, offset=10000, length=10000)` (the returned `next_offset`)
3. … repeat until `has_more` is `false`.

Negative values, or an `offset` greater than `total_length`, return an
`{"error": ..., ...}` payload (the latter includes `total_length`).

#### Deprecated: `full_text` and `content_truncated`

Earlier versions of `get_case` truncated `content` at 30,000 characters
unless `full_text=True` was passed (then at 100,000). Truncation has been
removed. For backwards compatibility:

- `full_text` is still accepted (`true` or `false`) but **ignored**; the
  content is always complete. Passing it adds a `deprecation_warnings` list
  to the response (and logs a server-side warning) telling the client to drop
  the argument and use `offset`/`length` for snippets.
- `content_truncated` is still returned alongside `content` and is always
  `false`.

Note that in the same release `content` switched from HTML to plain text;
clients that need the HTML can use the REST API (`/api/cases/<id>/`,
`/api/laws/<id>/`).

Both will be removed in a future release; clients should stop sending
`full_text` and stop reading `content_truncated`.

### Cross-References

| Tool | Description | Backend |
|------|-------------|---------|
| `validate_citation` | Check if Aktenzeichen, ECLI, or § reference exists in the database | SQL |
| `get_case_references` | Forward refs: which laws and cases does a decision cite? | SQL |
| `get_citing_cases` | Reverse refs: which cases cite a given decision? | Elasticsearch |
| `get_cases_for_law` | All cases interpreting a specific statute section; `sort=date|most_cited` (landmark first) | Elasticsearch |

The same data is queryable via the
[REST API's citation surfaces](api/api-overview.md#citations--cross-references):
nested actions like `/api/cases/<id>/references/` for case-by-case
lookups, plus a flat `/api/references/` resource with slug-based
filters (`cited_by_law__book__slug=bgb&cited_by_law__slug=823`) for
cross-cutting graph queries the MCP tools can't express. The REST
nested actions and the MCP tools share a single service layer and
the same backends — `references` / forward-refs paths via the ORM,
`citing_cases` paths via Elasticsearch — so payload shapes match.

When Elasticsearch is unavailable, `get_citing_cases` and
`get_cases_for_law` return a structured error envelope rather than
silently degrading:

```json
// Transient timeout — same query is sub-100ms after segments are
// paged in. Agent should wait + retry.
{"error": "Search timed out…", "retryable": true, "hint": "…"}

// Hard outage — retrying immediately won't help.
{"error": "Citation graph is temporarily unavailable. Try again in a few minutes.", "retryable": false}
```

Agents should branch on `retryable` rather than parsing the message.
See [docs/elasticsearch.md](elasticsearch.md#index-fields-driving-citation-lookups)
for the underlying `CaseIndex.cited_laws` / `CaseIndex.cited_cases`
fields.

### Statistics

| Tool | Description |
|------|------------|
| `get_case_statistics` | Aggregated counts by court, year, jurisdiction |

## Usage Examples

### Legal Research

> "Find BGH decisions from 2023 about § 823 BGB"

1. `search_cases(query="§ 823 BGB", court_code="BGH", start_date="2023-01-01", end_date="2023-12-31")`
2. `get_case(case_id=12345)` for full text (or `get_case(case_id=12345, length=10000)` to read it in plain-text chunks)
3. `get_case_references(case_id=12345)` for cited laws/cases

### Citation Verification

> "Is 'VI ZR 123/22' a valid BGH file number?"

1. `validate_citation(citation="VI ZR 123/22")`

### Legislative Impact Analysis

> "How is § 1004 BGB interpreted in case law?"

1. `get_cases_for_law(book_code="BGB", section="1004")`
2. `get_case(case_id=...)` for relevant decisions

## Design Principles

- **Verbatim text only**: No AI-generated summaries. The agent summarizes; we provide the source.
- **Search → Retrieve pattern**: Search returns snippets; `get_case`/`get_law_section` returns full text.
- **Citation validation**: Built-in hallucination guard for legal citations.
- **No truncation**: Retrieval tools return the complete text. Agents that need to protect their context window request plain-text snippets via `offset`/`length` instead of relying on a server-side cut-off.

## Disclaimer

This data is provided for informational purposes only and is not a substitute for professional legal advice. References are automatically extracted and may be incomplete. Verify critical citations against the full text.

## Technical Details

- **Transport**: Streamable HTTP at `/mcp`
- **Package**: `django-mcp-server` v0.5.7
- **OAuth**: `django-oauth-toolkit` v3.x
- **Search**: Elasticsearch 7.17 via django-haystack
