import logging

from django.core.management import BaseCommand
from django.db import models, transaction

from oldp.apps.laws.models import LawBook

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Set latest revision of law books"

    def __init__(self):
        super(Command, self).__init__()

    def handle(self, *args, **options):
        # Fetch latest revision date per code
        latest_revisions = (
            LawBook.objects.values("code")
            .annotate(max_date=models.Max("revision_date"))
            .order_by("code")
        )

        # Update each code atomically to avoid race conditions.
        # When multiple rows share the same max revision_date for a code
        # (which happens for books imported on the same day), break the
        # tie by highest pk so exactly ONE row ends up with latest=True.
        # Without this tie-break, every duplicate gets latest=True and
        # ``Law.get_latest_revision_url`` raises
        # ``MultipleObjectsReturned`` on every request — see also
        # ``dedupe_latest_books`` for cleaning up existing duplicates.
        with transaction.atomic():
            for rev in latest_revisions:
                code = rev["code"]
                max_date = rev["max_date"]

                keeper_pk = (
                    LawBook.objects.filter(code=code, revision_date=max_date)
                    .order_by("-pk")
                    .values_list("pk", flat=True)
                    .first()
                )
                if keeper_pk is None:
                    continue

                LawBook.objects.filter(pk=keeper_pk).update(latest=True)

                LawBook.objects.filter(code=code).exclude(pk=keeper_pk).update(
                    latest=False
                )

                logger.debug(
                    f"Set latest for: {code} (pk={keeper_pk}, revision_date={max_date})"
                )
