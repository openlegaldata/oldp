# Data Dumps & Bulk Downloads

For bulk access to OLDP data, the `dump_api_data` management command exports
every public API resource to gzipped JSONL files, accompanied by a
`manifest.json` describing the snapshot. This is the canonical way OLDP
publishes its data — including the [HuggingFace dataset
`openlegaldata/court-decisions-germany`](https://huggingface.co/datasets/openlegaldata/court-decisions-germany)
(produced from a dump via [`oldp-toolkit`](https://github.com/openlegaldata/oldp-toolkit)).

## Usage

```bash
./manage.py dump_api_data ./workingdir/snapshot-2026-04-29 --override
```

Arguments:

- `output` (positional) — directory path relative to `WORKING_DIR`.
- `--override` — replace an existing output directory.
- `--limit N` — cap the number of records per resource (default `0` = unlimited).

## Output layout

```
snapshot-2026-04-29/
├── cases.jsonl.gz
├── courts.jsonl.gz
├── laws.jsonl.gz
├── law_books.jsonl.gz
├── cities.jsonl.gz
├── states.jsonl.gz
├── countries.jsonl.gz
├── annotation_labels.jsonl.gz
├── case_annotations.jsonl.gz
├── case_markers.jsonl.gz
└── manifest.json
```

Each `*.jsonl.gz` contains one record per line, serialized using the same
serializer the public REST API uses, so the dump shape mirrors the API.

## Snapshot contract

The dump command guarantees the following properties:

### Always-accepted filter

Records on `Case`, `Law`, `LawBook`, and `Court` always have
`review_status == "accepted"`. Pending or declined records are never written
to a dump and therefore never reach published artifacts.

### Stable ordering

Records are written in ascending primary-key order. Given the same database
state, two consecutive dump runs produce byte-identical files. This makes
downstream snapshots (HuggingFace dataset versions, benchmark resolution
indices) reproducible.

### Self-describing manifest

`manifest.json` records the snapshot identity:

```json
{
  "snapshot_date": "2026-04-29T12:34:56+00:00",
  "oldp_version": "0.9.13",
  "filters": {"review_status": "accepted"},
  "files": {
    "cases.jsonl.gz": {"row_count": 318442},
    "laws.jsonl.gz": {"row_count": 47821},
    "law_books.jsonl.gz": {"row_count": 612},
    "courts.jsonl.gz": {"row_count": 1284}
  }
}
```

Downstream consumers should pin against `snapshot_date` so that benchmark
scores or analyses remain reproducible across OLDP database growth.

## Citation-friendly fields

Some serializers denormalize fields that would otherwise require joining
multiple JSONL files:

- **`laws.jsonl.gz`** records carry a `book_code` field (the parent
  `LawBook.code`) so a citation matcher can build a
  `(book_code, slug) -> law_id` index without loading `law_books.jsonl.gz`.
- **`courts.jsonl.gz`** records carry both `code` (canonical, ECLI-derived)
  and `aliases` (newline-separated alternative names like "BGH" /
  "Bundesgerichtshof") for resolving citations to a `court_id`.

## Downstream consumers

- [`oldp-toolkit`](https://github.com/openlegaldata/oldp-toolkit) reads
  `cases.jsonl.gz` (auto-detects the `.gz` suffix), converts HTML to
  Markdown, extracts inline reference markers, and publishes the result as
  a HuggingFace parquet dataset.
