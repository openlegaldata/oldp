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
| **Authenticated** | OAuth 2.0 login with OLDP account | 1,000 requests/hour (per user) |

### OAuth Flow

The server implements OAuth 2.0 with PKCE and Dynamic Client Registration (RFC 7591). Discovery endpoints:

- `/.well-known/oauth-protected-resource` — Resource metadata
- `/.well-known/oauth-authorization-server` — Authorization server metadata
- `/oauth/register/` — Dynamic Client Registration
- `/oauth/authorize/` — Authorization endpoint
- `/oauth/token/` — Token endpoint

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
| `search_cases` | Full-text search via Elasticsearch. Returns snippets, not full text. Accepts citation-graph filters (`cited_law_book` + `cited_law_section` or `cited_case_id`) that compose with the keyword query — e.g. "cases citing § 823 BGB that mention 'Mietrecht'" |
| `search_laws` | Full-text search across law sections. Returns snippets only |
| `get_similar_cases` | Cases textually similar to a given case (Elasticsearch `more_like_this`). For comparative research from one on-point decision |
| `filter_cases` | Structured ORM filtering by court, date, file number, ECLI, etc. |

See [Search](searching.md) for the full filter matrix and combined-search
examples across all three surfaces.

### Retrieval

| Tool | Description |
|------|------------|
| `get_case` | Full case by ID/slug. Truncated at 30k chars; use `full_text=True` for 100k |
| `get_law_section` | Law text by book code + section (e.g. "BGB" + "823") |
| `get_court` | Detailed court info: name, address, contact, case count |

### Cross-References

| Tool | Description | Backend |
|------|-------------|---------|
| `validate_citation` | Check if Aktenzeichen, ECLI, or § reference exists in the database | SQL |
| `get_case_references` | Forward refs: which laws and cases does a decision cite? | SQL |
| `get_citing_cases` | Reverse refs: which cases cite a given decision? | Elasticsearch |
| `get_cases_for_law` | All cases interpreting a specific statute section | Elasticsearch |

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
2. `get_case(case_id=12345)` for full text
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
- **Content truncation**: Cases truncated at 30k chars by default to protect context windows.

## Disclaimer

This data is provided for informational purposes only and is not a substitute for professional legal advice. References are automatically extracted and may be incomplete. Verify critical citations against the full text.

## Technical Details

- **Transport**: Streamable HTTP at `/mcp`
- **Package**: `django-mcp-server` v0.5.7
- **OAuth**: `django-oauth-toolkit` v3.x
- **Search**: Elasticsearch 7.17 via django-haystack
