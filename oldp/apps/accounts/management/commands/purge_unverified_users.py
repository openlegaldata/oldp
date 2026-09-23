"""Delete never-verified / spam signups (manual command, no email sent).

Abandoned signups and signup spam never confirm their email address. After a
grace period they are deleted outright — no email is sent (the address was
never confirmed). This is separate from the inactive-account lifecycle
(``warn_inactive_users`` / ``purge_inactive_users``), which only ever touches
*verified* accounts.

Scriptable by design:

    python manage.py purge_unverified_users --dry-run        # list, delete nothing
    python manage.py purge_unverified_users --limit 100 --yes  # delete a batch

Token-created content survives deletion (``created_by_token`` is ``SET_NULL``).
A line ``ELIGIBLE_TOTAL=<n>`` is always printed so a wrapper can loop in
batches.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from oldp.apps.accounts import lifecycle


class Command(BaseCommand):
    help = "Delete never-verified, abandoned/spam signups (no email is sent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the accounts that would be deleted; delete nothing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Delete at most N accounts (oldest signups first). Use for batching.",
        )
        parser.add_argument(
            "--grace-days",
            type=int,
            default=None,
            help="Override the unverified grace period (days since signup).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive confirmation prompt (non-interactive).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        yes = options["yes"]

        now = timezone.now()
        if options["grace_days"] is not None:
            cutoff = now - timedelta(days=options["grace_days"])
        else:
            cutoff = lifecycle.unverified_cutoff(now)

        qs = lifecycle.unverified_users_to_purge(cutoff)
        total = qs.count()

        self.stdout.write(
            f"Unverified signups joined before {cutoff:%Y-%m-%d} with no "
            f"confirmed email, no social login and no login activity."
        )
        self.stdout.write(f"ELIGIBLE_TOTAL={total}")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to delete."))
            return

        # The set we will actually act on this run (oldest first, capped).
        targets = list(qs[:limit] if limit else qs)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN — {len(targets)} account(s) would be deleted:"
                )
            )
            for user in targets:
                self.stdout.write(
                    f"  #{user.pk} {user.username} <{user.email}> "
                    f"(joined {user.date_joined:%Y-%m-%d})"
                )
            return

        if not yes:
            answer = input(f"Delete {len(targets)} unverified account(s)? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                self.stdout.write("Aborted.")
                return

        deleted = 0
        for user in targets:
            label = f"#{user.pk} {user.username} <{user.email}>"
            user.delete()
            deleted += 1
            self.stdout.write(f"  deleted {label}")

        remaining = lifecycle.unverified_users_to_purge(cutoff).count()
        self.stdout.write(f"REMAINING_ELIGIBLE={remaining}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} account(s). Remaining eligible: {remaining}."
            )
        )
