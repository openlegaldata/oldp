"""Re-file cases that were assigned to the wrong court, using their own ECLI.

For each ``<filed-under>:<ecli-says>`` pair, walks the cases currently filed
under the first court and re-points those whose ECLI court segment names the
second one. Anything else is left alone, so an unrelated decision sitting
under the same court is never touched. The misfiled rows kept an intact ECLI
naming the deciding court, which is what makes the repair deterministic
rather than heuristic.

Reports by default, writes only under ``--write``. The resolver bug behind
these rows is fixed in #276 — deploy that first, or fresh misfilings arrive
behind the repair. Re-filing rewrites the slug, so every repaired case
changes URL and the old one starts returning 404; accepted deliberately, see
the PR discussion.

Only audited pairs are repaired by default: an ECLI that disagrees with the
court is not always a misfiling, so run ``audit_ecli_court_mismatch`` to
justify a new pair before adding one here.

See ``docs/data-repairs.md`` for the operational procedure — run order,
counter meanings, and what to do when a run does not finish.
"""

import logging
from collections import Counter

from django.core.management import BaseCommand, CommandError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.signals import post_save
from haystack import connection_router, connections
from haystack.exceptions import NotHandled

from oldp.apps.cases.cache import invalidate_case_cache
from oldp.apps.cases.models import Case
from oldp.apps.cases.services.court_resolver import court_code_from_ecli
from oldp.apps.cases.signals import sync_case_to_search_index_on_save
from oldp.apps.courts.models import Court

logger = logging.getLogger(__name__)

# ``<filed-under>:<ecli-says>``. Both were checked against the public
# court table on 2026-09-20: all four codes exist, each target court
# carries no aliases of its own, and each source court has an alias line
# the target's short name is a substring of — ``OVG Berlin`` swallowing
# ``VG Berlin``, ``OLG Rostock`` swallowing ``LG Rostock``. Replaying
# ``_find_by_alias`` over all 1119 courts turns up no third pair.
#
# Add one only once ``audit_ecli_court_mismatch`` lists it without an
# annotation *and* both codes exist: an unverified default is a run that
# aborts before the verified pairs get their turn.
DEFAULT_PAIRS = ("OVGBEBB:VGBE", "OLGROST:LGROSTO")

# ``(counter key, label)`` in report order. The labels are also the column
# the report is aligned to, so a new row cannot desync the two.
SUMMARY_ROWS = (
    ("scanned", "Cases scanned"),
    ("reassigned", "Cases re-filed"),
    # Not "names another court": the branch catches every ECLI that is not
    # the move target, and the correctly-filed majority is in there.
    ("other_ecli", "Skipped (ECLI does not name the target)"),
    ("no_ecli", "Skipped (no usable ECLI)"),
    ("no_file_number", "Skipped (no file number)"),
    ("duplicate", "Skipped (duplicate at target)"),
    ("slug_collision", "Skipped (slug collision)"),
    ("write_conflict", "Skipped (write conflict)"),
)
# Reported once per run, not per pair: the search index is written in a
# single bulk pass covering every pair.
INDEXED_ROW = ("indexed", "Documents re-indexed")

# What to do about a stale index, which is the opposite advice depending on
# whether the walk finished. Kept out of the error ``_reindex`` raises: that
# text is printed in both situations, and the wrong half of this pair read
# as a flat contradiction of the line next to it.
INDEX_REBUILD = (
    "Run `manage.py update_index cases` to rebuild — do not re-run this command."
)
INDEX_REBUILD_THEN_RESUME = (
    "Run did not finish and the index is stale. Rebuild it with "
    "`manage.py update_index cases` first, then re-run this command to move "
    "what is left."
)


class ReportState:
    """Moves a report decided on but did not write.

    Empty under ``--write``, where the database has every committed move
    and answers the pre-checks on its own. Shared across pairs rather than
    per pair: two pairs can name the same target court, and one pair's
    target can be another pair's source.
    """

    def __init__(self):
        self.claimed_slugs = set()
        self.claimed_file_numbers = set()
        self.moved_pks = set()

    def record(self, case, target_key):
        """Remember a move, both what it takes and what it frees.

        The file number is keyed as written. Case-folding it would match
        MySQL's ``_ci`` collation and mismatch a case-sensitive one just
        as widely, and the only rows affected are ones whose file numbers
        differ by case alone across two pairs aimed at the same court.
        """
        self.claimed_slugs.add(case.slug)
        self.claimed_file_numbers.add(target_key)
        self.moved_pks.add(case.pk)

    def blocked_by(self, blocker_pk):
        """Whether a row a pre-check found is really still in the way.

        A row this run has moved is not: the database still shows it at
        its old slug and file number only because a report writes nothing.
        """
        return blocker_pk is not None and blocker_pk not in self.moved_pks


class Command(BaseCommand):
    help = "Re-file cases whose ECLI names a different court than the one assigned"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pair",
            action="append",
            default=None,
            metavar="FILED_UNDER:ECLI_SAYS",
            help=(
                "Move cases filed under the first court code to the second "
                "when their ECLI names the second. Repeatable. Defaults to: "
                f"{', '.join(DEFAULT_PAIRS)}."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help=(
                "Re-file at most this many cases per pair (0 = no limit). "
                "Counts the cases actually moved, not the ones walked past."
            ),
        )
        parser.add_argument(
            "--write",
            action="store_true",
            default=False,
            help=(
                "Actually re-file the cases. Without it the command only "
                "reports what it would change."
            ),
        )

    def handle(self, *args, **options):
        pairs = self._parse_pairs(options["pair"] or DEFAULT_PAIRS)
        limit = options["limit"]
        if limit < 0:
            # argparse takes -1 as a value, and the walk then reads
            # ``0 >= -1`` as "already at the limit" and reports an
            # all-zeros run as success.
            raise CommandError("--limit cannot be negative; use 0 for no limit")
        dry_run = not options["write"]

        totals = Counter()
        reindex_pks = []
        report = ReportState()

        # The per-save hook ships one ES round-trip per case and swallows
        # its own failures (``signals.py``), so a flaky index would leave
        # wrong-court documents behind a clean report. Re-indexed in one
        # bulk pass below instead, where a failure is visible.
        hook_was_connected = post_save.disconnect(
            sync_case_to_search_index_on_save, sender=Case
        )
        # Cleared at the end of the loop rather than read back from
        # ``sys.exc_info()`` in the ``finally``: that reports whatever
        # exception is being handled anywhere up the stack, so a caller
        # invoking the command from inside its own ``except`` block would
        # have a clean run called aborted — and an indexing failure
        # printed instead of raised, which exits 0 on a stale index.
        failed = True
        try:
            for filed_under, ecli_says in pairs:
                self.stdout.write(
                    f"{filed_under.code} -> {ecli_says.code} "
                    f"({filed_under.name} -> {ecli_says.name})"
                )
                counters = Counter()
                try:
                    self._walk_pair(
                        filed_under,
                        ecli_says,
                        dry_run=dry_run,
                        limit=limit,
                        counters=counters,
                        reindex_pks=reindex_pks,
                        report=report,
                    )
                finally:
                    # Owned here, not returned, so an abort mid-pair still
                    # reports what that pair managed to do — the rows are
                    # committed either way.
                    self._write_counters(counters)
                    totals.update(counters)
            failed = False
        finally:
            if hook_was_connected:
                post_save.connect(sync_case_to_search_index_on_save, sender=Case)
            # Every move is committed by its own ``atomic()`` as it happens,
            # so an aborted run still has rows to index. Indexing them here
            # rather than after the loop keeps search from naming the old
            # court for cases that already moved.
            self._finish(
                totals,
                reindex_pks,
                dry_run=dry_run,
                failed=failed,
            )

    def _finish(self, totals, reindex_pks, dry_run, failed):
        """Index what was moved and print the summary, complete run or not.

        Args:
            totals: Run-wide counters.
            reindex_pks: Primary keys of the cases re-filed so far.
            dry_run: Nothing was written, so nothing needs indexing.
            failed: The run is unwinding from an exception.
        """
        index_error = None
        if not dry_run and reindex_pks:
            try:
                self._reindex(reindex_pks, totals)
            except Exception as exc:
                # Held, not raised: the counters below describe committed
                # rows and must reach the operator either way.
                index_error = exc

        self.stdout.write("")
        self.stdout.write("Total")
        self._write_counters(totals, indexed=not dry_run)
        if dry_run:
            self.stdout.write(
                "Report only: no rows were written. Pass --write to apply."
            )
        if index_error is not None:
            self.stdout.write(str(index_error))

        if failed and dry_run:
            # A report commits nothing, so the usual "the cases counted
            # above are committed" would contradict the line printed just
            # above it.
            self.stdout.write(
                "Run did not finish. Nothing was written; the counters above "
                "cover only the rows reached before the failure."
            )
        elif failed and index_error is None:
            self.stdout.write(
                "Run did not finish. The cases counted above are committed; "
                "re-running resumes from what is left."
            )
        elif failed:
            # Both at once. A re-run is the only thing that moves the rows
            # the abort left behind, and it cannot repair the index — the
            # rows already moved are no longer under the source court for
            # the walk to hand to ``_reindex`` — so the two instructions
            # are ordered rather than left to contradict each other.
            self.stdout.write(INDEX_REBUILD_THEN_RESUME)
        elif index_error is not None:
            self.stdout.write(INDEX_REBUILD)

        # Not raised while already unwinding: it would replace the failure
        # the operator needs to see with a consequence of it, and it has
        # been printed above either way.
        if index_error is not None and not failed:
            raise CommandError(f"{index_error} {INDEX_REBUILD}") from index_error

    def _walk_pair(
        self,
        filed_under,
        ecli_says,
        dry_run,
        limit,
        counters,
        reindex_pks,
        report,
    ):
        """Re-file the cases under ``filed_under`` whose ECLI names ``ecli_says``.

        Args:
            filed_under: Court the cases are currently filed under.
            ecli_says: Court their ECLI names, and the move target.
            dry_run: Report without writing.
            limit: Stop after re-filing this many cases (0 = no limit). Per
                pair, and counted on the cases moved rather than the ones
                walked past: most of what this walks belongs where it is, so
                a limit on rows *seen* would be consumed by the first pair
                long before the second one ran.
            counters: Tallies, keyed by the names in ``SUMMARY_ROWS``. Owned
                by the caller so they survive an abort.
            reindex_pks: Collects the pks of re-filed cases, for the caller's
                bulk search-index pass.
            report: Moves this run has decided on but not written. Empty
                under ``--write``. Owned by the caller because two pairs
                can meet at the same court.
        """
        # ``iterator()`` only streams on PostgreSQL; on MySQL (the recommended
        # production engine) the whole result set is materialised client-side,
        # so the blobs of every case under the source court would be resident
        # at once. Deferring them costs one extra SELECT per *saved* row —
        # ``save()`` re-snapshots ``content`` and the ES document template
        # renders ``get_text`` — and nothing for the majority that is skipped.
        cases = (
            Case.objects.filter(court=filed_under)
            .defer("content", "raw", "abstract")
            .order_by("pk")
        )

        for case in cases.iterator():
            if limit and counters["reassigned"] >= limit:
                break
            counters["scanned"] += 1

            segment = court_code_from_ecli(case.ecli)
            if not segment:
                counters["no_ecli"] += 1
                continue
            if segment.upper() != ecli_says.code.upper():
                counters["other_ecli"] += 1
                continue

            # ``file_number`` is nullable, and both guards below need it:
            # ``set_slug`` indexes into it, and a NULL is invisible to
            # ``unique_together`` so the duplicate pre-check cannot vouch for
            # the row either.
            if not case.file_number:
                counters["no_file_number"] += 1
                logger.debug("skip case=%s without a file number", case.pk)
                continue

            # Which row blocks, not just whether one does: under
            # ``unique_together`` there is at most one, and a report needs
            # to know whether it is a row the run has already moved away.
            # ``order_by()`` drops the model's ``-date`` from a lookup that
            # can match once.
            target_key = (ecli_says.pk, case.file_number)
            duplicate_pk = (
                Case.objects.filter(court=ecli_says, file_number=case.file_number)
                .exclude(pk=case.pk)
                .order_by()
                .values_list("pk", flat=True)
                .first()
            )
            if target_key in report.claimed_file_numbers or report.blocked_by(
                duplicate_pk
            ):
                counters["duplicate"] += 1
                logger.debug(
                    "skip case=%s duplicate at target court file_number=%r",
                    case.pk,
                    case.file_number,
                )
                continue

            old_slug = case.slug
            case.court = ecli_says
            case.set_slug()

            collision_pk = (
                Case.objects.filter(slug=case.slug)
                .exclude(pk=case.pk)
                .order_by()
                .values_list("pk", flat=True)
                .first()
            )
            if case.slug in report.claimed_slugs or report.blocked_by(collision_pk):
                counters["slug_collision"] += 1
                logger.debug("skip case=%s slug collision slug=%r", case.pk, case.slug)
                continue

            if dry_run:
                report.record(case, target_key)
                counters["reassigned"] += 1
                continue

            try:
                with transaction.atomic():
                    # Narrow write: the instance is a snapshot from
                    # ``iterator()`` and the run is long, so a full save would
                    # revert columns a concurrent writer touched meanwhile
                    # (``review_status`` above all).
                    case.save(update_fields=["court", "slug", "updated_date"])
            except (IntegrityError, Case.DoesNotExist) as exc:
                # Both unique constraints are pre-checked above, so reaching
                # here means another writer changed the row mid-run: took its
                # slug or file number, or deleted it — in which case
                # ``save()``'s trailing read of the deferred ``content``
                # raises ``DoesNotExist``. Counted apart from the pre-checks:
                # those are reproducible, this is a race a re-run may not hit.
                self._count_conflict(counters, case, exc)
                continue
            except DatabaseError as exc:
                # ``_save_table`` raises a *bare* ``DatabaseError`` when
                # ``update_fields`` matched no row — the other way a
                # concurrent delete surfaces. Subclasses mean something else
                # is wrong, and a dropped connection must not be logged six
                # thousand times as a conflict, so only the exact type is one.
                if type(exc) is not DatabaseError:
                    raise
                self._count_conflict(counters, case, exc)
                continue

            # Counted and queued before the cache call: the row is committed
            # by now, so a cache backend that throws must not make the move
            # vanish from the report or from the search-index pass.
            counters["reassigned"] += 1
            reindex_pks.append(case.pk)
            # post_save invalidates the new slug; the old one would keep
            # serving a cached page for a URL that no longer resolves.
            if old_slug:
                invalidate_case_cache(old_slug)

    @staticmethod
    def _count_conflict(counters, case, exc):
        """Record a row another writer took or removed mid-run."""
        counters["write_conflict"] += 1
        logger.debug(
            "skip case=%s write conflict slug=%r file_number=%r (%s)",
            case.pk,
            case.slug,
            case.file_number,
            exc.__class__.__name__,
        )

    def _write_counters(self, counters, indented=True, indented_by="  ", indexed=False):
        """Print a counter block, every label padded to one column.

        The alignment is computed from ``SUMMARY_ROWS`` rather than typed in,
        so adding a row cannot leave the block ragged.

        Args:
            counters: ``Counter`` to render; missing keys print as 0.
            indented: Indent the rows under their heading.
            indented_by: Indent string used when ``indented``.
            indexed: Also render the ``indexed`` row (only meaningful after a
                write, where the bulk search-index pass has run).
        """
        rows = SUMMARY_ROWS + (INDEXED_ROW,) if indexed else SUMMARY_ROWS
        width = max(len(label) for _, label in rows) + 1
        prefix = indented_by if indented else ""
        for key, label in rows:
            self.stdout.write(f"{prefix}{(label + ':'):<{width}} {counters[key]}")

    def _reindex(self, case_pks, totals, batch_size=500):
        """Push the re-filed cases into the search index in bulk.

        Args:
            case_pks: Primary keys of the cases that were re-filed.
            totals: Run-wide counters; ``indexed`` is raised per batch.
                Owned by the caller for the same reason the walk's are: a
                failure in the last batch must not erase the ones before
                it from the summary.
            batch_size: Cases handed to the backend per round-trip.

        Raises:
            CommandError: If the backend rejected a batch. Unlike the
                per-save hook this does not swallow the failure: the court
                is part of the indexed document, so a silent miss would
                leave search filtering the repaired cases under the old
                court.
        """
        for using in connection_router.for_write():
            try:
                index = connections[using].get_unified_index().get_index(Case)
            except NotHandled:
                continue
            # The whole pass is guarded, not just ``update``: fetching the
            # rows can fail too, and every failure here means the same thing
            # to the operator.
            try:
                backend = connections[using].get_backend()
                for start in range(0, len(case_pks), batch_size):
                    chunk = case_pks[start : start + batch_size]
                    # ``index_queryset`` carries the prefetch chain that keeps
                    # ``prepare_*`` free of per-row SQL, and is already limited
                    # to accepted cases — the only ones the index holds. So a
                    # run that moves pending or rejected rows reports fewer
                    # documents than cases, which is correct and not a partial
                    # failure.
                    rows = list(index.index_queryset(using=using).filter(pk__in=chunk))
                    backend.update(index, rows)
                    # Documents written, so a second write backend would
                    # count each case again. One is configured, and the
                    # alternative — counting cases and calling them
                    # documents — would be the less honest number.
                    totals["indexed"] += len(rows)
            except Exception as exc:
                raise CommandError(
                    f"{len(case_pks)} cases were re-filed and committed, "
                    f"but indexing failed after {totals['indexed']} documents: "
                    f"{exc}."
                ) from exc

    @staticmethod
    def _parse_pairs(raw_pairs):
        """Resolve ``FILED_UNDER:ECLI_SAYS`` strings to ``Court`` instances.

        Args:
            raw_pairs: Iterable of ``"<code>:<code>"`` strings.

        Returns:
            List of ``(filed_under, ecli_says)`` Court tuples.

        Raises:
            CommandError: On a malformed pair or an unknown court code.
        """
        pairs = []
        for raw in raw_pairs:
            parts = raw.split(":")
            if len(parts) != 2 or not all(p.strip() for p in parts):
                raise CommandError(
                    f"Malformed --pair {raw!r}, expected FILED_UNDER:ECLI_SAYS"
                )
            filed_under_code, ecli_code = (p.strip() for p in parts)
            try:
                # ``iexact`` like ``_find_by_ecli`` and the walk's own
                # ``code.upper()`` comparison; an exact lookup would reject
                # ``--pair ovgbebb:vgbe`` on a case-sensitive collation.
                filed_under = Court.objects.get(code__iexact=filed_under_code)
                ecli_says = Court.objects.get(code__iexact=ecli_code)
            except Court.DoesNotExist as exc:
                raise CommandError(f"Unknown court code in --pair {raw!r}") from exc
            except Court.MultipleObjectsReturned as exc:
                # ``code`` is unique, but on a case-sensitive collation that
                # lets ``VGBE`` and ``vgbe`` both exist, and the lookup above
                # is deliberately case-insensitive.
                raise CommandError(
                    f"Ambiguous court code in --pair {raw!r}: more than one "
                    "court matches it apart from case"
                ) from exc
            if filed_under.pk == ecli_says.pk:
                raise CommandError(f"--pair {raw!r} names the same court twice")
            pairs.append((filed_under, ecli_says))
        return pairs
