"""Deactivate, then anonymize, warned-but-still-inactive accounts (manual).

Phases 2 & 3 of the inactive-account lifecycle (see ``accounts.lifecycle``).
Run **manually** by an operator, typically some time after
``warn_inactive_users``:

  * Deactivate — accounts whose warning deadline has passed without a login are
    set ``is_active=False`` (reversible; an admin can flip it back).
  * Anonymize — accounts deactivated longer ago than the deactivation grace get
    their personal data scrubbed and tokens disabled. Token-created content is
    kept (cases/laws/courts survive, attribution dropped).

    python manage.py purge_inactive_users --dry-run   # show what would happen
    python manage.py purge_inactive_users             # apply

By default both phases run. Use --deactivate-only or --anonymize-only to run
one at a time.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from oldp.apps.accounts import lifecycle


class Command(BaseCommand):
    help = (
        "Deactivate then anonymize accounts that ignored the inactivity "
        "warning (manual cleanup step)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change; change nothing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N accounts per phase.",
        )
        parser.add_argument(
            "--deactivate-only",
            action="store_true",
            help="Only run the deactivation phase.",
        )
        parser.add_argument(
            "--anonymize-only",
            action="store_true",
            help="Only run the anonymization phase.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        run_deactivate = not options["anonymize_only"]
        run_anonymize = not options["deactivate_only"]
        now = timezone.now()

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will change."))

        if run_deactivate:
            self._run_deactivate(now, limit, dry_run)
        if run_anonymize:
            self._run_anonymize(now, limit, dry_run)

    def _run_deactivate(self, now, limit, dry_run):
        qs = lifecycle.users_to_deactivate(now).order_by("pk")
        total = qs.count()
        if limit is not None:
            qs = qs[:limit]
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Deactivate: {total} account(s)"))

        count = 0
        for user in qs.iterator():
            deadline = user.profile.deletion_scheduled_for
            self.stdout.write(
                f"  #{user.pk} {user.username} <{user.email}> "
                f"(deadline {deadline:%Y-%m-%d})"
            )
            if not dry_run:
                lifecycle.deactivate_user(user, now=now)
            count += 1

        verb = "would deactivate" if dry_run else "deactivated"
        self.stdout.write(self.style.SUCCESS(f"  {verb} {count} account(s)."))

    def _run_anonymize(self, now, limit, dry_run):
        qs = lifecycle.users_to_anonymize(now).order_by("pk")
        total = qs.count()
        if limit is not None:
            qs = qs[:limit]
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Anonymize: {total} account(s)"))

        count = 0
        for user in qs.iterator():
            deactivated = user.profile.deactivated_at
            self.stdout.write(
                f"  #{user.pk} {user.username} <{user.email}> "
                f"(deactivated {deactivated:%Y-%m-%d})"
            )
            if not dry_run:
                lifecycle.anonymize_user(user, now=now)
            count += 1

        verb = "would anonymize" if dry_run else "anonymized"
        self.stdout.write(self.style.SUCCESS(f"  {verb} {count} account(s)."))
