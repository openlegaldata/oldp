"""Send the inactivity warning email to dormant accounts (manual command).

Phase 1 of the inactive-account lifecycle (see ``accounts.lifecycle``). Finds
dormant, eligible, not-yet-warned accounts and emails each a one-off,
administrative warning with a login deadline, then records the deadline.

This command is meant to be run **manually** by an operator. Mail goes out in
batches with a pause between them (spam/reputation protection).

    python manage.py warn_inactive_users --dry-run   # print recipients + text
    python manage.py warn_inactive_users             # actually send

Logging in before the deadline cancels the deletion (handled in
``accounts.signals``).
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from oldp.apps.accounts import lifecycle


class Command(BaseCommand):
    help = "Email dormant accounts an inactivity warning (manual cleanup step)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print recipients and the full email text; send nothing, "
            "change nothing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N accounts (useful for a cautious first run).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=settings.INACTIVE_USER_MAIL_BATCH_SIZE,
            help="Emails to send before pausing (default from settings).",
        )
        parser.add_argument(
            "--batch-delay",
            type=int,
            default=settings.INACTIVE_USER_MAIL_BATCH_DELAY,
            help="Seconds to pause between batches (default from settings).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        batch_size = max(1, options["batch_size"])
        batch_delay = max(0, options["batch_delay"])

        now = timezone.now()
        cutoff = lifecycle.dormancy_cutoff(now)
        deadline = lifecycle.warning_deadline(now)

        qs = lifecycle.users_to_warn(cutoff).order_by("pk")
        total = qs.count()
        if limit is not None:
            qs = qs[:limit]

        self.stdout.write(
            f"Dormancy cutoff: {cutoff:%Y-%m-%d} "
            f"(no login/token use since). "
            f"Deletion deadline for warned users: {deadline:%Y-%m-%d}."
        )
        self.stdout.write(
            f"Found {total} account(s) to warn"
            + (f"; processing {min(limit, total)}." if limit else ".")
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be sent."))

        sent = 0
        for index, user in enumerate(qs.iterator(), start=1):
            if dry_run:
                subject, body = lifecycle.render_warning_email(user, deadline)
                last_login = (
                    f"{user.last_login:%Y-%m-%d}" if user.last_login else "never"
                )
                self.stdout.write("")
                self.stdout.write("=" * 78)
                self.stdout.write(
                    f"To: {user.email}  (user #{user.pk} {user.username}, "
                    f"last_login={last_login})"
                )
                self.stdout.write(f"Subject: {subject}")
                self.stdout.write("-" * 78)
                self.stdout.write(body)
                sent += 1
                continue

            if lifecycle.send_warning_email(user, deadline):
                lifecycle.mark_warned(user.profile, deadline, now=now)
                sent += 1
                self.stdout.write(f"  warned #{user.pk} {user.email}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"  FAILED  #{user.pk} {user.email} (see logs)")
                )

            # Spam protection: pause between batches.
            if not dry_run and sent and sent % batch_size == 0:
                self.stdout.write(
                    f"  …sent {sent}; pausing {batch_delay}s before next batch."
                )
                time.sleep(batch_delay)

        verb = "would warn" if dry_run else "warned"
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done — {verb} {sent} account(s)."))
