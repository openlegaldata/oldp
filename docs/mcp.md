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

The `whoami` tool (and `GET /api/whoami/` on the REST side) reports this from inside a conversation: whether the connection is signed in, the rate-limit tier, and how much of the budget is left. See [Account](#account).

### OAuth Flow

The server implements OAuth 2.0 with PKCE and Dynamic Client Registration (RFC 7591). Discovery endpoints:

- `/.well-known/oauth-protected-resource` — Resource metadata
- `/.well-known/oauth-authorization-server` — Authorization server metadata
- `/oauth/register/` — Dynamic Client Registration
- `/oauth/authorize/` — Authorization endpoint
- `/oauth/token/` — Token endpoint

The consent screen shown at `/oauth/authorize/` overrides django-oauth-toolkit's default template with `oldp/assets/templates/oauth2_provider/authorize.html` (OLDP micro layout, styles in `scss/oldp/_oauth.scss`). The template lives in the project template dir rather than the `mcp` app because `oauth2_provider` precedes `oldp.apps.mcp` in `INSTALLED_APPS`, so an app-level override would be shadowed.

### Sign-in for write tools

The endpoint is open to anonymous callers. A `tools/call` of a tool that
needs an account (`SIGN_IN_REQUIRED_TOOLS` in `oldp/apps/mcp/views.py`,
currently only `submit_feedback`) without credentials is answered with HTTP
401 instead of a tool result:

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api",resource_metadata="https://de.openlegaldata.io/.well-known/oauth-protected-resource/mcp"

{"message": "submit_feedback requires a signed-in connection. ...", "code": "not_authenticated"}
```

This is the MCP authorization challenge: a client whose connector signs in
only when the server asks (claude.ai: "Required when the server asks") shows
its Connect prompt and retries after the OAuth flow. Every other 401 from
`/mcp` (invalid or expired token) carries the same `resource_metadata`
attribute, after any `error="invalid_token"` from django-oauth-toolkit.

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
| `search_cases` | Full-text search via Elasticsearch. Returns snippets, not full text. Accepts citation-graph filters (`cited_law_book` + `cited_law_section` or `cited_case_id`) that compose with the keyword query — e.g. "cases citing § 823 BGB that mention 'Mietrecht'". `sort=relevance\|date\|most_cited` (most_cited = landmark precedent; other values return an error, the applied `sort` is echoed in the response); each result carries `citing_cases_count`, and with relevance sort also `match_quality` (high/medium/low), which is left out for the other sorts |
| `search_laws` | Full-text search across law sections. Returns snippets only. `book_code` filters by law book in any case (`BranntwMonG`, `branntwmong`); an unknown code returns an error with `suggestions` |
| `get_similar_cases` | Cases textually similar to a given case (Elasticsearch `more_like_this`). For comparative research from one on-point decision |
| `filter_cases` | Structured ORM filtering by court, date, file number, ECLI, etc. |

See [Search](searching.md) for the full filter matrix and combined-search
examples across all three surfaces.

`filter_cases` returns the newest cases first with `total` and `has_more`.
Each of its database queries runs under a time limit
(`DJANGO_MCP_DB_STATEMENT_TIMEOUT`, default 3 seconds; MariaDB
`max_statement_time`, `0` disables it). Keep twice the value below the
gunicorn worker timeout, since one call runs up to two limited queries.
When a query runs out of time:

```json
// The exact count took too long: the page is complete, total is a lower bound.
{"total": 21, "has_more": true, "total_is_lower_bound": true, "message": "…", "results": […]}

// The page itself took too long, e.g. a rare decision_type with no court or
// date filter (substring match, no index). Narrow the filters.
{"error": "This filter combination is too broad to answer in time.", "retryable": false, "hint": "…"}
```

### Retrieval

| Tool | Description |
|------|------------|
| `get_case` | Full case by ID/slug: metadata plus complete (untruncated) plain-text `content`. Optional `offset`/`length` return a snippet instead (see below) |
| `get_law_section` | Law text by book code + section (e.g. "BGB" + "823"), complete plain-text `content`. Supports the same `offset`/`length` snippet mode. `section` accepts the bare number or any prefix spelling (`§ 823`, `§823`, `Art. 20`, `Art 20`, `Artikel 20`), whatever spelling the book stores; only exact sections match (never `§ 1823` for `823`). A miss returns a `hint` showing how the book labels its sections |
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
| `get_case_references` | Forward refs: which laws and cases does a decision cite? A law reference extracted before the latest revision of its book was imported is shown as the same section of the latest revision (when it still exists there) | SQL |
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

### Account

| Tool | Description |
|------|------------|
| `whoami` | Who the connection is signed in as (or anonymous), how it authenticated, the rate-limit tier and the remaining budget, plus how to get a larger one |

Example response for an anonymous Claude connector user:

```json
{
  "authenticated": false,
  "user": null,
  "auth_method": null,
  "rate_limit": {
    "tier": "anonymous",
    "bucket": "shared",
    "limit": 500,
    "window_seconds": 3600,
    "used": 212,
    "remaining": 288,
    "retry_after_seconds": null
  },
  "upgrade": {
    "action": "sign_up",
    "url": "https://de.openlegaldata.io/accounts/signup/",
    "limit": "5000 requests/hour",
    "message": "You are not signed in. Anonymous requests from this client share one budget with all other anonymous users of the same connector. Create a free account and connect with OAuth (MCP) or send an API token (REST API) to get your own budget of 5000 requests/hour."
  }
}
```

- `tier`: `anonymous`, `registered` (default signed-in budget), `enriched` (profile-completion bonus) or `custom` (per-token limit set by an admin).
- `bucket`: `shared` when all anonymous users of the connector share one budget (requests from Anthropic's IP range), `ip` for other anonymous clients, `user` for signed-in users (shared between MCP and the REST API).
- `used` / `remaining` count HTTP requests in the sliding window, including the `whoami` call itself. `retry_after_seconds` is set only when nothing is left.
- `upgrade` suggests `sign_up` to anonymous callers and `complete_profile` to signed-in users without the bonus; it is `null` otherwise.

The budget is read from the throttles' own cache buckets, so it matches what the next request will be judged against. `GET /api/whoami/` returns the same shape for the REST API's budget (see [API overview](api/api-overview.md#throttle-rates)).

### Feedback

| Tool | Description |
|------|------------|
| `submit_feedback` | Send a feature request, bug report or data issue to the OLDP team. **Signed-in users only** (OAuth or API token); anonymous calls get HTTP 401 with an OAuth challenge (see [Sign-in for write tools](#sign-in-for-write-tools)) |

The agent-facing counterpart of the [contact form](https://de.openlegaldata.io/contact/): the input is
emailed to `SITE_EMAIL` via Django's email backend, with the account's email
address as `Reply-To`, so the team can answer. Arguments:

- `category`: `feature_request`, `bug_report`, `data_issue` or `other`
- `message`: the feedback, 20–5000 characters
- `subject` (optional): one-line summary, max 200 characters; defaults to the
  first line of the message
- `context` (optional): technical context such as tool calls, case IDs or
  law references, max 2000 characters

The email also names the user, how they authenticated and, for OAuth, the
connector (OAuth application name). Each user can submit at most
`DJANGO_MCP_FEEDBACK_DAILY_LIMIT` (default 10) messages per day; failed
deliveries return `retryable: true` and don't count. The tool docstring asks
agents to submit only with the user's consent and without personal data.

### Tool titles and annotations

Every tool carries a human-readable `title` and MCP
[tool annotations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#tool-annotations),
which clients use for display and to decide whether a call needs user
confirmation. All OLDP tools except `submit_feedback` only read OLDP's own
data:

| Annotation | Read-only tools | `submit_feedback` |
|------------|-----------------|-------------------|
| `readOnlyHint` | `true` | `false` (sends an email) |
| `destructiveHint` | `false` | `false` |
| `idempotentHint` | `true` | `false` (each call sends one email) |
| `openWorldHint` | `false` | `false` |

django-mcp-server registers toolset methods without titles or annotations,
so `oldp/apps/mcp/annotations.py` sets them on startup
(`MCPConfig.ready()`). **When adding a tool, add its title to `TOOL_TITLES`**
in that module (and its hints to `TOOL_HINTS` unless it is read-only); `oldp/apps/mcp/tests/test_annotations.py` fails for any
registered tool without one.

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

## Directory Listings

### Official MCP Registry

Each country deployment (de, later at, ch) is listed as its own server in
the [official MCP Registry](https://registry.modelcontextprotocol.io), which
many other directories (Glama, mcp.directory, PulseMCP, ...) import from.
Instead of a checked-in `server.json`, the registry document is generated
from the deployment's settings by a management command:

| `server.json` field | Source |
|---------------------|--------|
| `name` | `MCP_REGISTRY_NAME`, e.g. `io.openlegaldata/de` |
| `title` | `MCP_REGISTRY_TITLE` (max. 100 characters) |
| `description` | `MCP_REGISTRY_DESCRIPTION` (max. 100 characters) |
| `version` | `oldp.__version__` |
| `websiteUrl`, `remotes` | `SITE_URL` (or `--site-url`), remote = `<site>/mcp` (Streamable HTTP) |
| `icons` | `<STATIC_URL>images/logo.svg` and `logo.png` (unhashed paths) |
| `repository` | `https://github.com/openlegaldata/oldp` |

The three `MCP_REGISTRY_*` settings are empty in core and set by the country
theme (e.g. `oldp_de.settings`); they can also be given as
`DJANGO_MCP_REGISTRY_*` env vars. The command refuses to run while they are
empty, invalid or longer than the registry allows, and requires an `https://`
site URL. It needs no database or search backend.

Publishing uses the
[`mcp-publisher`](https://github.com/modelcontextprotocol/registry/releases) CLI.
One-time setup — generate a key pair (OpenSSL 3+) and print the public record:

```bash
openssl genpkey -algorithm Ed25519 -out mcp-registry-key.pem
```

```bash
echo "v=MCPv1; k=ed25519; p=$(openssl pkey -in mcp-registry-key.pem -pubout -outform DER | tail -c 32 | base64)"
```

Add the printed line as a DNS TXT record on the apex domain
`openlegaldata.io`. This proves control of `io.openlegaldata/*` (and all
subdomains), so it covers every country listing. Then, after each release:

```bash
export DJANGO_SETTINGS_MODULE=oldp_de.settings DJANGO_CONFIGURATION=ProdDEConfiguration
./manage.py mcp_server_json --output server.json
```

```bash
mcp-publisher login dns --domain openlegaldata.io \
  --private-key "$(openssl pkey -in mcp-registry-key.pem -noout -text | grep -A3 'priv:' | tail -n +2 | tr -d ' :\n')"
```

```bash
mcp-publisher publish server.json
```

The registry accepts each version only once, so changed metadata is published
with a new OLDP release.
Registry names cannot be renamed after the first publish.

Alternatively, an instance can serve the HTTP proof itself: set
`DJANGO_MCP_REGISTRY_AUTH` to the printed `v=MCPv1; ...` line, which is then
served at `/.well-known/mcp-registry-auth` (404 while unset), and log in with
`mcp-publisher login http --domain de.openlegaldata.io --private-key ...`.
HTTP verification only covers that exact host, so the name must then be
`io.openlegaldata.de/<server>`.

### Claude connector directory

Submissions go through the directory portal in the claude.ai admin settings
(see [Anthropic's submission guide](https://claude.com/docs/connectors/building/submission)).
The review requires tool titles and annotations (see
[above](#tool-titles-and-annotations)), OAuth for authenticated access, and a
privacy policy: <https://de.openlegaldata.io/pages/privacy/>.

## Disclaimer

This data is provided for informational purposes only and is not a substitute for professional legal advice. References are automatically extracted and may be incomplete. Verify critical citations against the full text.

## Technical Details

- **Transport**: Streamable HTTP at `/mcp`
- **Package**: `django-mcp-server` v0.5.7
- **OAuth**: `django-oauth-toolkit` v3.x
- **Search**: Elasticsearch 7.17 via django-haystack
- **Rejected requests**: every 4xx answer from `/mcp` is logged by
  `oldp.mcp.transport` as `mcp_request_rejected` with the status, the
  JSON-RPC method (never the arguments), `MCP-Protocol-Version`,
  `Content-Type`, `Accept`, body size, user agent and the reason from the
  response body. Requests fail there before any tool runs: a body that is not
  JSON (DRF, while OAuth2 authentication reads the form data), a body that is
  not one JSON-RPC message or an unsupported protocol version (MCP SDK), bad
  credentials or throttling. The access log only has the status code.
