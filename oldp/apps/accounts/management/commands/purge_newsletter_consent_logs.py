"""Delete newsletter consent log chains whose retention period has run out.

Retention rule (privacy policy, section "Newsletter"): the proof of a consent
is kept until three years after the end of the year in which the consent was
revoked (regelmäßige Verjährungsfrist, §§ 195, 199 BGB). A "chain" is every
log row for the same user/e-mail address up to and including the revocation.
Rows written after a later re-subscription are untouched.

Run weekly from the deployment cron (see deployment README). Idempotent.
"""

from datetime import datetime
from datetime import timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from oldp.apps.accounts.models import NewsletterConsentLog

RETENTION_YEARS = 3


def retention_expired_before(now=None):
    """Return the latest revocation timestamp whose chain may be deleted now.

    A revocation in year Y expires on 1 January of Y + RETENTION_YEARS + 1, so
    everything revoked in or before year ``now.year - RETENTION_YEARS - 1`` is
    due.
    """
    now = now or timezone.now()
    cutoff_year = now.year - RETENTION_YEARS
    return datetime(cutoff_year, 1, 1, tzinfo=dt_timezone.utc)


class Command(BaseCommand):
    help = (
        "Delete newsletter consent log rows whose retention period "
        f"({RETENTION_YEARS} years after the end of the revocation year) has expired."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be deleted.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cutoff = retention_expired_before()
        revocations = NewsletterConsentLog.objects.filter(
            action=NewsletterConsentLog.ACTION_REVOKED, created_at__lt=cutoff
        ).order_by("created_at")

        total = 0
        for revoked in revocations:
            chain_filter = Q(email=revoked.email)
            if revoked.user_id is not None:
                chain_filter |= Q(user_id=revoked.user_id)
            chain = NewsletterConsentLog.objects.filter(
                chain_filter, created_at__lte=revoked.created_at
            )
            count = chain.count()
            total += count
            if dry_run:
                self.stdout.write(
                    f"would delete {count} row(s) for {revoked.email} "
                    f"(revoked {revoked.created_at:%Y-%m-%d})"
                )
            else:
                chain.delete()

        verb = "Would delete" if dry_run else "Deleted"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {total} consent log row(s) revoked before {cutoff:%Y-%m-%d}."
            )
        )
