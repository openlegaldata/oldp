# Content moderation: takedowns and redactions in court decisions

Published decisions come from official portals, anonymised by the courts.
Occasionally a decision still identifies a person (a party, a witness, health or
criminal data), or a judge or lawyer objects to being named. The privacy policy
(`/pages/privacy/`, section "Melde- und Entfernungsverfahren") promises:

- every report is reviewed within **14 days**,
- identifiable data of parties or Art. 9/10 data is **redacted or the decision
  removed**, also when identifiability only follows from combined facts,
- removed passages **stay removed when the decision is imported again**,
- the record keeps only the decision id and what was removed, never the
  reporter's contact data.

This page is the implementation of that promise.

## Why a reported decision is never deleted

The ingestor only *creates* cases (`POST /api/cases/`); it never updates an
existing one. `CaseCreator.check_duplicate` rejects a submission whose
`(court, file_number)` already exists with **409 Conflict**. That unique key is
therefore the only thing that keeps a removed decision from coming back on the
next crawl. Deleting the row drops the key, and the decision reappears.

So a takedown keeps the row and hides it instead:

| Channel | How a `rejected` case disappears |
|---|---|
| Website, REST API, MCP | `Case.get_queryset()` / `filter_by_review_status` only return `accepted` |
| Elasticsearch | `post_save` signal (`sync_case_to_search_index_on_save`) removes the document |
| Detail-view cache | `post_save` signal invalidates the slug-keyed cache |
| Sitemap | built from `Case.get_queryset()` |
| Dumps (`dump_api_data`) and the Hugging Face datasets built from them | hard-filtered to `accepted` |

Already downloaded dumps cannot be recalled; the next dump no longer contains
the case.

## Review fields

Next to `review_status` the `Case` model carries:

- `review_date` — set automatically on save whenever `review_status` or
  `review_note` changes (and on creation). `bulk_approve_cases` stamps it too.
- `review_note` — staff-only free text: report reference (date, our
  ticket/e-mail id), what was removed or redacted, legal category (party data,
  Art. 9, Art. 10, function-related name), decision taken. Deferred from list
  views; not part of any serializer, dump or export.

## The guard: bulk review never touches accepted or rejected items

A taken-down case is `rejected` with a `review_note`. Nothing that works in
bulk may ever flip it back:

| Path | Rule |
|---|---|
| `set_review_accepted` / `set_review_rejected` steps (cases, courts, laws, law books; admin actions and `process_*` commands) | act on **pending** items only, others are skipped and logged |
| `set_review_pending` steps | reset **accepted** items only; rejected items are skipped (a rejected → pending → accepted chain would re-publish a takedown) |
| `set_lawbook_review_*` cascade to laws | same rules per law |
| `bulk_approve_cases` | selects `review_status="pending"` only |
| REST `PATCH /api/cases/<id>/ {"review_status": "accepted"}` (staff) | refused while the case is rejected **and** has a `review_note` |

The only way back is a deliberate single edit in the admin change form
(clear or amend `review_note`, set the status).

## Procedure

1. **Log the report** in the mailbox with a reference; do not copy the
   reporter's name or address into oldp.
2. **Assess** within 14 days using the categories of the privacy policy:
   - identifiable party/witness data or Art. 9/10 data → redact or take down,
     no balancing needed;
   - function-related name (judge, lawyer, expert) → case-by-case balancing;
     remove only with a concrete reason (e.g. endangerment).
3. **Redaction** (the decision stays online): open the case in the admin, edit
   `content` (replace the passage with `[…]`), write the report reference and
   what was removed into `review_note`, and **clear `raw`** — it still holds
   the unredacted crawler HTML (`Case.mark_redacted(note)` does the last two
   steps programmatically). No processing step rebuilds `content` from `raw`.
   Re-run `extract_refs` afterwards so the citation markers match the text.
4. **Takedown** (the decision goes offline): select the case(s) in the admin
   list, run the action **"Takedown: hide from all channels and purge text"**.
   It sets `rejected`, blanks `content`, `raw` and `abstract` and appends who
   did it to `review_note`. Then add the report reference and reason.
5. **Inform the source** (court / portal) about the insufficient
   anonymisation where appropriate, and answer the reporter.
6. **False report**: edit the case in the admin, note the outcome in
   `review_note`, set `review_status` back to `accepted`.

## Programmatic use

```python
case.apply_takedown(note="Report 2026-10-06 #12: party identifiable, Art. 9 data")
case.save()
case.mark_redacted(note="Report 2026-10-06 #13: witness name removed, para. 4")
case.save()
```
