# The OLDP ecosystem

OLDP is the core of a small ecosystem of independent, MIT-licensed projects.
The core platform (this repository) stores and serves legal data; the sister
projects feed data in, theme it, and process exports back out. Each is a
separately installable Python package.

## Projects at a glance

| Project | Role | Entry point | Repository |
| ------- | ---- | ----------- | ---------- |
| **oldp** | Core Django web app — models, REST API, search, MCP server | Django app / `manage.py` | [openlegaldata/oldp](https://github.com/openlegaldata/oldp) |
| **oldp-de** | German theme & country-specific settings (templates, static assets, German court types) | Django settings module `oldp_de.settings` | [openlegaldata/oldp-de](https://github.com/openlegaldata/oldp-de) |
| **oldp-ingestor** | Scrapers & API clients that pull German laws and court decisions from 13+ sources and push them into OLDP | CLI: `oldp-ingestor` | [openlegaldata/oldp-ingestor](https://github.com/openlegaldata/oldp-ingestor) |
| **oldp-toolkit** | Dump preprocessing — converts OLDP data dumps into HuggingFace / Parquet / JSONL datasets | CLI: `oldpt` | [openlegaldata/oldp-toolkit](https://github.com/openlegaldata/oldp-toolkit) |

## How data flows

```text
   External sources                  ┌─────────────────────────────┐
 (RIS, GII, Bayern, NRW,             │            OLDP             │
  Juris, EUR-Lex, …)                 │   (this repository)         │
        │                            │                             │
        │   scrape / API fetch       │  • Cases, Laws, Courts      │
        ▼                            │  • References / citations   │
 ┌───────────────┐   REST API POST   │  • Elasticsearch search     │
 │ oldp-ingestor │ ────────────────▶ │  • REST API + MCP server    │
 └───────────────┘                   │  • Themed by  ◀── oldp-de   │
                                     └──────────────┬──────────────┘
                                                    │  dump_api_data
                                                    ▼
                                         gzipped JSONL snapshot
                                          (+ manifest.json)
                                                    │
                                                    ▼
                                         ┌────────────────────┐
                                         │    oldp-toolkit    │
                                         └─────────┬──────────┘
                                                   ▼
                                   HuggingFace dataset / Parquet
                                  (openlegaldata/court-decisions-germany)
```

## oldp-de: German theme

[oldp-de](https://github.com/openlegaldata/oldp-de) is a pluggable Django theme
package that adapts OLDP for German legal data without modifying the core
platform. It provides:

- Alternative Django templates and static assets (German UI), found ahead of
  the core templates by the template loader.
- German-specific configuration classes (`DevDEConfiguration`,
  `ProdDEConfiguration`) layered on top of OLDP's base settings.
- The `courts_de` app, contributing 40+ German court types (AG, LG, OLG, BGH,
  BVerfG, BAG, BSG, BFH, …) and ECLI mapping data.

Deploy it by pointing `DJANGO_SETTINGS_MODULE` at `oldp_de.settings`. See
[Architecture → Themes](architecture.md#themes) and the
[Configuration reference](configuration.md).

## oldp-ingestor: data ingestion

[oldp-ingestor](https://github.com/openlegaldata/oldp-ingestor) is a standalone
CLI tool that fetches German laws and court decisions from external providers
and writes them into OLDP through the REST API (or to local JSON files).

- Providers for RIS, GII, RII, Bayern, NRW, Niedersachsen, EUR-Lex and several
  Juris state variants, built on a shared HTTP / scraper / Playwright base.
- Polite by default: request pacing, exponential backoff, and `Retry-After`
  handling.
- Authenticates against OLDP with an API token (see
  [REST API → Authentication](api/api-overview.md)).

The data it writes lands in OLDP's content models and is then refined by the
[processing pipeline](processing.md) (court resolution, reference extraction).

## oldp-toolkit: dump preprocessing

[oldp-toolkit](https://github.com/openlegaldata/oldp-toolkit) consumes the
gzipped JSONL snapshots produced by OLDP's `dump_api_data` command (see
[Data Dumps & Bulk Downloads](data-dumps.md)) and converts them into
distribution formats:

- HTML → Markdown conversion and inline legal-reference extraction.
- Output as HuggingFace Hub dataset, HuggingFace on-disk dataset, Parquet, or
  JSONL.
- Powers the public
  [`openlegaldata/court-decisions-germany`](https://huggingface.co/datasets/openlegaldata/court-decisions-germany)
  dataset.
