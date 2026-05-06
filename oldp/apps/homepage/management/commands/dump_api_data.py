import gzip
import json
import logging
import os
import shutil
from datetime import datetime, timezone

from django.conf import settings
from django.core.management import BaseCommand
from django.core.paginator import Paginator

from oldp.api.urls import router
from oldp.utils.version import get_version

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Export data to gzipped JSONL using API serializers.

    Each registered API resource is written to ``<plural>.jsonl.gz``. A
    ``manifest.json`` file is written alongside, recording the snapshot
    date, OLDP version, applied filters, and per-file row counts so that
    downstream consumers (e.g. ``oldp-toolkit``, citation-matching
    benchmarks) can pin against a specific snapshot.

    Records with ``review_status`` are always filtered to ``"accepted"``
    — non-accepted records must never appear in published artifacts.

    By default, only the latest revision of each ``LawBook`` (and its
    associated ``Law`` rows) is dumped. Pass ``--include-lawbook-revisions``
    to export every historical revision instead.

    Pagination iterates rows in ascending primary-key order so the same
    prod state yields a byte-stable dump across runs.

    Usage::

        python manage.py dump_api_data ./workingdir/dumps

    """

    help = "Export API data as gzipped JSONL with manifest"
    chunk_size = 1000

    REVIEW_STATUS_FILTER = "accepted"

    def add_arguments(self, parser):
        parser.add_argument(
            "output",
            type=str,
            help="Path relative to working directory ({})".format(settings.WORKING_DIR),
        )

        parser.add_argument(
            "--override",
            action="store_true",
            default=False,
            help="Override existing output files",
        )

        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max. number of records per content type (default: 0, 0=unlimited)",
        )

        parser.add_argument(
            "--include-lawbook-revisions",
            action="store_true",
            default=False,
            help=(
                "Include all LawBook revisions (and their child Laws) in the "
                "dump. By default only books with latest=True are exported."
            ),
        )

    def handle(self, *args, **opts):
        dir_path = os.path.join(settings.WORKING_DIR, opts["output"])

        if os.path.exists(dir_path):
            if opts["override"]:
                shutil.rmtree(dir_path)
            else:
                logger.error("Output directory exist already: %s", dir_path)
                return

        os.mkdir(dir_path)

        include_lawbook_revisions = opts["include_lawbook_revisions"]

        files_manifest = {}
        for api_register in router.registry:
            plural, view_set_cls, _singular = api_register

            if "/" in plural or plural == "users":
                logger.debug("Skip non-root endpoints (and users): %s", plural)
                continue

            file_name = plural + ".jsonl.gz"
            file_path = os.path.join(dir_path, file_name)
            view_set = view_set_cls()
            serializer_cls = view_set.get_serializer_class()
            qs = view_set.get_queryset()

            model = qs.model
            field_names = {f.name for f in model._meta.get_fields()}
            if "review_status" in field_names:
                qs = qs.filter(review_status=self.REVIEW_STATUS_FILTER)

            if not include_lawbook_revisions:
                if model.__name__ == "LawBook":
                    qs = qs.filter(latest=True)
                elif model.__name__ == "Law":
                    qs = qs.filter(book__latest=True)

            qs = qs.order_by("pk")

            if opts["limit"] > 0:
                qs = qs[: opts["limit"]]

            logger.debug("Writing to %s", file_path)

            row_count = 0
            with gzip.open(file_path, "wt", encoding="utf-8") as fh:
                paginator = Paginator(qs, self.chunk_size)
                for page in range(1, paginator.num_pages + 1):
                    logger.debug(
                        "%s - total %i - page %i / %i",
                        plural,
                        paginator.count,
                        page,
                        paginator.num_pages,
                    )
                    for item in paginator.page(page).object_list:
                        data = serializer_cls(instance=item).data
                        fh.write(json.dumps(data, ensure_ascii=False) + "\n")
                        row_count += 1

            files_manifest[file_name] = {"row_count": row_count}

        manifest = {
            "snapshot_date": datetime.now(timezone.utc).isoformat(),
            "oldp_version": get_version(),
            "filters": {
                "review_status": self.REVIEW_STATUS_FILTER,
                "include_lawbook_revisions": include_lawbook_revisions,
            },
            "files": files_manifest,
        }
        manifest_path = os.path.join(dir_path, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False)

        logger.info("Done")
