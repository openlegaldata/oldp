# Data Repairs

Ingestion bugs leave rows behind after the bug itself is fixed. This page
covers the repair commands that clean them up, and the order to run them
in — these commands rewrite production data, so the sequence matters more
than the flags.

## Cases filed under the wrong court

### What happened

`CourtResolver._find_by_alias` matched court names with an unanchored
`aliases__icontains`. Every `VG <Ort>` is a substring of the corresponding
`OVG <Ort>`, so a portal sending the *correct* name `"VG Berlin 1. Kammer"`
had its case filed under Oberverwaltungsgericht Berlin-Brandenburg, whose
alias list carries the line `OVG Berlin`. Verwaltungsgericht Berlin has no
aliases of its own and could never win the match.

The resolver fix is #276: `_find_by_alias` accepts a name only when it
equals a whole alias line, or appears as whole words in the alias lines of
exactly one court *of the same court type* (so `AG Bingen` still finds
`AG Bingen am Rhein`, but `VG Berlin` never matches `OVG Berlin`).
**Deploy it before running the repair below.** The repair only rewrites
rows that already exist, so against the old resolver it finishes with a
fresh batch of misfilings arriving behind it.

The rows already written keep the wrong `court` foreign key.

The ECLI on those rows is intact and still names the deciding court, so
the repair is deterministic rather than heuristic: `ECLI:DE:VGBE:…` on a
case filed under `OVGBEBB` can only mean the case belongs to `VGBE`.

### Step 1 — find the pairs worth repairing

    python manage.py audit_ecli_court_mismatch

Read-only. It walks the whole corpus, compares each case's ECLI court
segment with its assigned court, and groups the disagreements:

    filed under  ECLI says  rows  note
    OVGBEBB      VGBE       6143
    AGGE1        AGGE2      3     same court name — likely duplicate Court rows
    OVGBEBB      NOSUCH     2     no Court with this code

**A disagreement is not automatically a misfiling.** Two kinds are
annotated and should be left alone:

- `no Court with this code` — the ECLI uses an abbreviation that is not in
  the court table. Usually a different abbreviation scheme, not a misfiled
  case.
- `same court name` — the two codes belong to `Court` rows sharing a name
  (AGGE1/AGGE2). The case is filed correctly; it is the *court table* that
  needs cleaning.

A third annotation, `ambiguous court code`, is not a verdict but a refusal
to give one: several `Court` rows carry that code differing only in case,
so the audit cannot tell which of them the group belongs to. Fix the court
table before reading anything into such a group — and note that
`reassign_courts_from_ecli` rejects a `--pair` naming such a code outright.

Rows with no annotation are the repair candidates. `--top N` caps the
table, `--min-rows N` drops the tail.

### Step 2 — report the repair

    python manage.py reassign_courts_from_ecli

**The command reports by default and writes only under `--write`**, so a
forgotten flag costs a report rather than thousands of moved rows. Without
`--pair` it uses the audited defaults, `OVGBEBB:VGBE` and
`OLGROST:LGROSTO`; add `--pair FILED_UNDER:ECLI_SAYS` (repeatable) for
others. A pair only becomes a default once the audit lists it unannotated
and both of its court codes have been checked against the court table.

Each pair gets its own block, followed by a `Total`:

    OVGBEBB -> VGBE (Oberverwaltungsgericht Berlin-Brandenburg -> Verwaltungsgericht Berlin)
      Cases scanned:                           11537
      Cases re-filed:                          6130
      Skipped (ECLI does not name the target): 5163
      Skipped (no usable ECLI):                231
      Skipped (no file number):                0
      Skipped (duplicate at target):           13
      Skipped (write conflict):                0

    Total
      ...

Note how the audit's 6,143 splits: 6,130 rows move, and 13 are the same
decision already filed correctly under VGBE — same file number, mostly
the same date — which no repair can merge for you.

What the skips mean:

| Counter | Meaning |
|---|---|
| ECLI does not name the target | The ECLI names some other court — **including the correctly-filed majority, whose ECLI names the court they are already under**. Not a backlog. |
| no usable ECLI | Nothing deterministic to move the row to. |
| no file number | The column is nullable, and a NULL is invisible to the duplicate pre-check. |
| duplicate at target | `unique_together(court, file_number)` — the decision is already filed correctly and this row needs a manual merge. |
| write conflict | Another writer took or deleted the row mid-run. Zero in a report; a re-run usually clears it. |

Every skip is decided *before* the write, so the report's counters are the
ones the write will produce — including for the moves the run makes
itself. Under `--write` each move commits before the next row is looked
at, so the database has it; a report writes nothing, so it keeps track of
its own moves instead: what each one claims at the target court, and what
it vacates. Both matter once two pairs meet at one court, which they do
when they share a target or when one pair's target is another's source.

`Cases scanned` and `ECLI does not name the target` carry no such
promise. They count the rows the walk went past, and a write changes what
there is to go past: a row moved into a court is walked again by a later
pair reading that court, which in a report never moved and so is not
there. Only chained `--pair` arguments can do this; the audited defaults
are disjoint.

### Step 3 — apply

    python manage.py reassign_courts_from_ecli --write

`--limit N` re-files at most N cases **per pair** — it counts the cases
moved, not the ones walked past, so a sampling run reaches every pair.

The run also updates the search index. The per-save Elasticsearch hook is
disconnected for the duration and the re-filed cases are pushed in one
bulk pass at the end: per-save indexing would be thousands of sequential
round-trips, and that hook swallows its own failures, which would leave
documents naming the *old* court behind a clean report.

**`Documents re-indexed` is normally lower than `Cases re-filed`.** The
index only holds accepted cases, so pending and rejected rows move in the
database and are not written to it. That is the correct outcome, not a
partial failure. A document left behind for a case that was demoted while
Elasticsearch was down is a separate problem, and belongs to the
reconciliation script `scripts/prune_stale_es_docs.sh` in the internal
`deployment` repository rather than to this repair — see
`docs/elasticsearch.md`.

## Cases with a wrong or malformed ECLI (#255)

### What happened

Some source portals publish wrong ECLIs, and the ingestor copied them verbatim:

- **Another decision's ECLI.** The Berlin portal shows swapped ECLIs on pairs of decisions (`34 L 73.18 A` carries the ECLI of `18 L 43.18` and vice versa); NI-VORIS and the Hessen portal attach ECLIs of other courts' decisions (LG Hannover with LG Kiel's ECLI).
- **Repeated prefix.** The Hessen portal renders `ECLI:ECLI:DE:…`.

New cases are checked on creation (see "ECLI Checks" in `docs/api/case-creation.md`). The rows already stored are repaired with:

    python manage.py repair_case_eclis           # report
    python manage.py repair_case_eclis --write   # apply

### What the command does

- **Repeated prefix:** collapsed to a single `ECLI:`.
- **Wrong ECLI:** an ECLI is treated as wrong when neither its file-number digits nor its day and month match the case. It is **cleared only when OLDP holds its rightful owner**: exactly one case of the ECLI's court code, on the ECLI's date, with a matching file number. If that owner is then left without an ECLI, the cleared one is moved to it, which puts swapped pairs back.
- **No owner found:** the row is listed as `keep` and left unchanged. Check these by hand; the heuristic alone never clears an ECLI.

Only the `ecli` column is written: `updated_date` and the slug (URL) stay unchanged, and the per-save hook re-indexes each changed case.

A report run against prod on 2026-09-24 found 68 repeated prefixes, 16 wrong ECLIs with an owner (6 of which move to it) and 10 without one.

## When a run does not finish

Each move commits in its own transaction as it happens, so an aborted run
leaves committed rows behind. The command is built for that:

- Whatever was moved is still indexed, and the counters printed describe
  what actually happened.
- The closing line says the run did not finish. **Re-running is safe** —
  already-moved rows are no longer under the source court, so the walk
  resumes from what is left.

If the run finishes but indexing fails, the summary is still printed and
the command exits with:

    N cases were re-filed and committed, but indexing failed after M
    documents: … Run `manage.py update_index cases` to rebuild — do not
    re-run this command.

Follow it literally. The database is correct; only the index is stale, and
re-running the repair will not fix an index.

If a run manages **both** — it aborts *and* indexing fails — the two
instructions above contradict each other, so the command prints the order
instead: rebuild the index first, then re-run the repair to move what is
left. The rebuild has to come first because a re-run cannot reach the rows
that already moved; they are no longer under the source court the walk
reads.

## URLs are kept

A case's URL is its slug (`/case/<slug>`), and the slug was derived from
the court when the case was created. The repair changes the court and the
denormalised `court_jurisdiction` / `court_level_of_appeal` columns, but
**never the slug**, so every indexed URL keeps working:

    /case/ovgbebb-2018-12-20-2-k-178-17  →  the case, now under VG Berlin

The slug's court prefix then names the old court. That is cosmetic; a
changed URL would be a 404 for every search engine and external link.
Re-processing does not rewrite it either: `assign_court` keeps existing
slugs unless `DJANGO_CASE_ASSIGN_COURT_UPDATE_SLUG=True`.

Note that re-filing bumps `updated_date` on every moved row, which puts
them at the top of the homepage's "recent cases" list and gives their
sitemap entries today's `lastmod`.
