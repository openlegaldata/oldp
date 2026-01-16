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

        # Update each code atomically to avoid race conditions
        # First set the new latest=True, then unset old ones
        with transaction.atomic():
            for rev in latest_revisions:
                code = rev["code"]
                max_date = rev["max_date"]

                # First, mark the latest revision as latest=True
                updated = LawBook.objects.filter(
                    code=code, revision_date=max_date
                ).update(latest=True)

                # Then, mark all other revisions for this code as latest=False
                LawBook.objects.filter(code=code).exclude(
                    revision_date=max_date
                ).update(latest=False)

                logger.debug(
                    f"Set latest for: {code} (revision_date={max_date}, updated={updated})"
                )
