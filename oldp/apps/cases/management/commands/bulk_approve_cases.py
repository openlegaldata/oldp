"""Bulk approve pending cases directly via ORM (no API overhead).

Usage:
    # Dry run — show count only
    python manage.py bulk_approve_cases --dry-run

    # Approve all pending
    python manage.py bulk_approve_cases

    # Approve only cases from a specific state
    python manage.py bulk_approve_cases --state 9

    # Approve cases in a date range
    python manage.py bulk_approve_cases --date-after 2022-10-01 --date-before 2026-01-01

    # Approve and update the search index
    python manage.py bulk_approve_cases --update-index
"""

import logging

from django.core.management.base import BaseCommand

from oldp.apps.cases.models import Case

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Bulk approve pending cases (single UPDATE query, no per-row API calls)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Only show count, don't update")
        parser.add_argument("--state", type=int, default=None,
                            help="Filter by court state ID")
        parser.add_argument("--date-after", default=None,
                            help="Only cases on or after this date (YYYY-MM-DD)")
        parser.add_argument("--date-before", default=None,
                            help="Only cases on or before this date (YYYY-MM-DD)")
        parser.add_argument("--token", type=int, default=None,
                            help="Filter by API token ID (created_by_token_id)")
        parser.add_argument("--batch-size", type=int, default=10000,
                            help="Update in batches of N (default: 10000)")
        parser.add_argument("--update-index", action="store_true",
                            help="Update the search index for approved cases")

    def handle(self, *args, **options):
        qs = Case.objects.filter(review_status="pending")

        if options["state"]:
            qs = qs.filter(court__state_id=options["state"])
        if options["token"]:
            qs = qs.filter(created_by_token_id=options["token"])
        if options["date_after"]:
            qs = qs.filter(date__gte=options["date_after"])
        if options["date_before"]:
            qs = qs.filter(date__lte=options["date_before"])

        count = qs.count()
        logger.info("Pending cases matching filters: %s", f"{count:,}")

        if options["dry_run"]:
            logger.info("Dry run — no changes made.")
            return

        if count == 0:
            logger.info("Nothing to approve.")
            return

        # Batch update to avoid locking the entire table
        batch_size = options["batch_size"]
        update_index = options["update_index"]
        total_updated = 0
        while True:
            batch_ids = list(qs.values_list("id", flat=True)[:batch_size])
            if not batch_ids:
                break
            updated = Case.objects.filter(id__in=batch_ids).update(
                review_status="accepted"
            )
            total_updated += updated
            logger.info("  Approved %s / %s...", f"{total_updated:,}", f"{count:,}")

            if update_index:
                self._update_search_index(batch_ids)

        logger.info("Done. Approved %s cases.", f"{total_updated:,}")

    @staticmethod
    def _update_search_index(case_ids):
        """Update the search index for the given case IDs."""
        from haystack import connections

        backend = connections["default"].get_backend()
        unified_index = connections["default"].get_unified_index()
        index = unified_index.get_index(Case)

        cases = Case.objects.filter(id__in=case_ids).select_related(
            "court", "court__state"
        )
        if cases.exists():
            backend.update(index, cases)
            logger.info("  Updated search index for %d cases.", len(case_ids))
