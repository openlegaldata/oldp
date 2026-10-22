"""List email addresses that more than one account holds (read-only).

Run this before applying migration ``accounts.0015_unique_email_indexes``,
which refuses to add the unique email indexes while duplicates exist:

    python manage.py find_duplicate_emails            # report
    python manage.py find_duplicate_emails --check    # also exit 1 if any

For every shared address it prints each account that holds it, with the facts
needed to pick the one to keep (verified, primary, last login, social login).
It changes nothing. A line ``DUPLICATES_TOTAL=<n>`` is always printed. How to
resolve the duplicates is described in ``docs/bug-report-duplicate-emails.md``.
"""

from django.core.management.base import BaseCommand, CommandError

from oldp.apps.accounts.email_uniqueness import (
    accounts_for_email,
    find_duplicate_emails,
)

KINDS = {
    "user_email": "shared auth_user.email (blocks migration 0015)",
    "verified_email_address": "verified on several accounts (blocks migration 0015)",
    "cross": "auth_user.email of one account, verified address of another",
}


class Command(BaseCommand):
    help = "List email addresses shared by several accounts (changes nothing)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit with an error if any duplicate exists (for scripts/CI).",
        )

    def handle(self, *args, **options):
        found = find_duplicate_emails()

        kinds_by_email = {}
        for kind, emails in found.items():
            for email in emails:
                kinds_by_email.setdefault(email, []).append(kind)

        for email in sorted(kinds_by_email):
            self.stdout.write(self.style.WARNING(email))
            for kind in kinds_by_email[email]:
                self.stdout.write(f"  - {KINDS[kind]}")
            for user, addresses in accounts_for_email(email):
                self.stdout.write("    " + self._describe(user, email, addresses))

        total = len(kinds_by_email)
        if total:
            self.stdout.write("")
        self.stdout.write(f"DUPLICATES_TOTAL={total}")
        if options["check"] and total:
            raise CommandError(
                f"{total} email address(es) are held by several accounts."
            )

    @staticmethod
    def _describe(user, email, addresses):
        parts = [f"#{user.pk} {user.username}"]
        parts.append(
            "user.email" if user.email.lower() == email else "user.email=other"
        )
        for address in addresses:
            flags = [
                "verified" if address.verified else "unverified",
                *(["primary"] if address.primary else []),
            ]
            parts.append(f"EmailAddress({', '.join(flags)})")
        if not user.is_active:
            parts.append("inactive")
        if user.is_staff:
            parts.append("staff")
        providers = sorted(user.socialaccount_set.values_list("provider", flat=True))
        if providers:
            parts.append("social=" + ",".join(providers))
        parts.append(f"joined={user.date_joined:%Y-%m-%d}")
        parts.append(
            f"last_login={user.last_login:%Y-%m-%d}"
            if user.last_login
            else "never logged in"
        )
        return " | ".join(parts)
