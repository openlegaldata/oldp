# Static pages

`oldp.apps.pages` serves markdown files as static pages at `/pages/<slug>/`
(imprint, privacy policy, terms, ...).

- **Location:** files live in `MARKDOWN_PAGES_DIR`, where each `<slug>.md` becomes a page.
  - The default is `oldp/apps/pages/content/`.
  - Themes can point the setting elsewhere.
  - Deployments can override it with the `DJANGO_MARKDOWN_PAGES_DIR` env var, so the texts can live in a separate repository and be mounted into the container.
- **No file:** if no file exists for a slug, the view falls back to a database flatpage at `/<slug>/`, then to 404.
- **Markdown:** rendered with python-markdown and the extensions `meta`, `extra` (tables, fenced code, `attr_list`, `md_in_html`, ...), `sane_lists`, `smarty` and `toc`.
- **Title:** an optional `title:` meta header sets the page title. Otherwise the first `# H1` is used, then the slug.
- **Caching:** parsed pages are cached per process and re-parsed when the file's mtime changes, so an edited file shows up without a restart.

## Settings values in pages

Some pages mention values that are configured in Django settings, such as rate limits or the MCP endpoint URL. Hard-coding them means the page goes stale whenever a setting changes. Write a placeholder instead; it is filled at request time:

```markdown
Without an account you can make {{ limits.anon.count }} requests per
{{ limits.anon.period }}; with an account {{ limits.user.count }} per
{{ limits.user.period }}.

MCP server: `{{ urls.mcp }}`
```

renders (English, default rate limits, `SITE_URL=https://de.openlegaldata.io`) as:

> Without an account you can make 100 requests per day; with an account
> 5,000 per hour. MCP server: `https://de.openlegaldata.io/mcp`

### Available placeholders

| Placeholder | Value | Source |
|---|---|---|
| `limits.anon.count` / `.period` / `.raw` | e.g. `100` / `day` / `100/day` | `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["anon"]` |
| `limits.user.*` | e.g. `5,000` / `hour` | `…["user"]` (signed-in users, REST + MCP share it) |
| `limits.enriched.*` | e.g. `10,000` / `hour` | `…["enriched"]` (profile completed) |
| `limits.mcp_anon.*` | e.g. `500` / `hour` | `MCP_ANTHROPIC_ANON_RATE` |
| `urls.site` | `https://…` | `SITE_URL` |
| `urls.api`, `urls.api_docs`, `urls.api_swagger`, `urls.api_schema` | API root, ReDoc, Swagger UI, OpenAPI JSON | `SITE_URL` + URL route |
| `urls.whoami`, `urls.mcp` | `/api/whoami/`, `/mcp` | `SITE_URL` + URL route |
| `urls.tokens`, `urls.signup`, `urls.profile` | API token page, sign-up, profile | `SITE_URL` + URL route |
| `version` | installed oldp version | `oldp.__version__` |

How the values are formatted:
- `.count` is localized with a thousands separator: `5,000` in English, `5.000` in German.
- `.period` is the translated singular unit: `hour` in English, `Stunde` in German.

### Rules

- **Lookups only:** placeholders are plain lookups in the table above. This is not the Django template engine: no tags, filters or expressions.
- **Escaping:** values are HTML-escaped. A placeholder also works inside code spans and blocks and in the `title:` header.
- **Unknown keys:** an unknown key is **left on the page as written** and logged as a warning (`oldp.apps.pages.variables`), so a typo is visible rather than blank. A deployment smoke check can grep the rendered page for `{{`.
- **Not the first line:** do not start a file with a line like `Key: {{ … }}`. The `meta` extension would read it as a header field. Start with a title header or a heading.
- **Other pages:** pages without placeholders are served exactly as before.
- **New placeholders:** add them to `page_variables()` in `oldp/apps/pages/variables.py` and to this table.
