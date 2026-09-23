"""Repair markers whose citation range expanded past the extraction cap.

``BaseExtractRefs._expand_range`` now refuses to expand a range wider than
``RANGE_EXPANSION_LIMIT``, keeping the start section only. Rows written before
that cap existed are still in the database -- production carried markers such
as ``§§ 154 bis 16617`` holding 16,464 ``Reference`` rows, nearly all pointing
at sections that do not exist.

This brings those markers to what the capped extractor would produce: the
single lowest-numbered reference is kept, the rest are deleted.

Re-running full extraction would also fix them, but costs far more and would
rewrite unrelated rows; this touches only the affected markers.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from oldp.apps.references.models import (
    CaseReferenceMarker,
    LawReferenceMarker,
    Reference,
)
from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Trim markers whose reference count exceeds the range-expansion cap"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=BaseExtractRefs.RANGE_EXPANSION_LIMIT,
            help="Markers with more references than this are repaired "
            f"(default: {BaseExtractRefs.RANGE_EXPANSION_LIMIT}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )
        parser.add_argument(
            "--max-markers",
            type=int,
            default=None,
            help="Stop after repairing this many markers.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        max_markers = options["max_markers"]

        total_markers = 0
        total_deleted = 0

        for model in (LawReferenceMarker, CaseReferenceMarker):
            through = model.references.through

            # Marker ids over the cap: aggregate on the through table rather
            # than loading any Reference rows.
            counts = (
                through.objects.values("marker_id")
                .order_by()
                .annotate(n=Count("id"))
                .filter(n__gt=limit)
            )

            for row in counts:
                marker_id = row["marker_id"]
                n = row["n"]
                if max_markers is not None and total_markers >= max_markers:
                    break

                ref_ids = list(
                    through.objects.filter(marker_id=marker_id).values_list(
                        "reference_id", flat=True
                    )
                )
                # Keep the lowest-numbered surviving reference: the capped
                # extractor emits the range's start section, and reference rows
                # are created in ascending range order, so the lowest pk is it.
                keep = min(ref_ids)
                drop = [r for r in ref_ids if r != keep]

                marker = model.objects.filter(pk=marker_id).first()
                label = (marker.text or "")[:60] if marker else "<missing>"
                self.stdout.write(
                    f"{model.__name__} {marker_id} {label!r}: "
                    f"{n} refs -> 1 (dropping {len(drop)})"
                )

                if not dry_run:
                    with transaction.atomic():
                        through.objects.filter(
                            marker_id=marker_id, reference_id__in=drop
                        ).delete()
                        Reference.objects.filter(pk__in=drop).delete()

                total_markers += 1
                total_deleted += len(drop)

        verb = "Would repair" if dry_run else "Repaired"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {total_markers} marker(s), "
                f"{'would delete' if dry_run else 'deleted'} {total_deleted} reference(s)."
            )
        )
