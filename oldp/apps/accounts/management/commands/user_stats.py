"""Print aggregate user statistics for a date range as JSON (read-only).

    python manage.py user_stats                       # last 30 days
    python manage.py user_stats --since 2026-09-01 --until 2026-09-30
    python manage.py user_stats --days 7 --free-text  # include profile texts

Counts only — no usernames, email addresses or ids. ``--free-text`` adds the
profile text fields (display name, organization, use case) without anything
that identifies the account. The report is meant to be read by a script or
by the internal-tools ``/user-stats`` skill; see ``docs/user-stats.md``.
"""

import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from oldp.apps.accounts.stats import user_stats


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Not a YYYY-MM-DD date: {value!r}") from exc


class Command(BaseCommand):
    help = "Print aggregate user statistics (signups, activation, logins, newsletter, profiles) as JSON."

    def add_arguments(self, parser):
        parser.add_argument("--since", type=_date, help="First day (YYYY-MM-DD).")
        parser.add_argument(
            "--until",
            type=_date,
            help="Last day, inclusive (YYYY-MM-DD). Default: today.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Range length when --since is not given (default 30).",
        )
        parser.add_argument(
            "--free-text",
            action="store_true",
            help="Include the profile free-text fields for a qualitative analysis.",
        )

    def handle(self, *args, **options):
        until = options["until"] or timezone.localdate()
        since = options["since"] or until - timedelta(days=options["days"] - 1)
        if since > until:
            raise CommandError("--since must not be after --until.")

        report = user_stats(since, until, include_free_text=options["free_text"])
        self.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
