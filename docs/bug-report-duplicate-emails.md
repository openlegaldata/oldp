# Duplicate Email Addresses

Several user accounts could share one email address. This page records the
bug, two related bugs found while investigating reports of missing
confirmation emails, the fixes, and the steps to deploy them. The deployment
needs a manual data cleanup before the migration can run.

## The bug

### Summary

Nothing in OLDP kept an email address on a single account. `auth_user.email`
has no unique constraint (stock Django). On MariaDB, allauth's
`unique_verified_email` constraint on `account_emailaddress` is never created.
The only remaining guard was allauth's signup form, and several other paths
went around it. Duplicates could be created through the "add email" page, the
Django admin, and direct model or command use.

### Environment

- django-allauth `>=65.1.0` (reproduced with 65.20.1), Django 5.2.
- Production: MariaDB 11 (see
  `oldp/apps/accounts/migrations/0006_convert_auth_tables_utf8mb4.py`).
- Settings at the time: `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`, and
  `ACCOUNT_UNIQUE_EMAIL` and `ACCOUNT_PREVENT_ENUMERATION` not set, so both
  used allauth's default `True`. Login is by username only. Users can add
  any number of extra addresses.

### Root cause 1: no unique index on MariaDB

allauth dropped `unique=True` from `EmailAddress.email` in 0.55 (migration
`account.0004_alter_emailaddress_drop_unique_email`). It replaced it with a
conditional constraint (`account.0003_…_create_unique_verified_email`):

```python
UniqueConstraint(fields=["email"], name="unique_verified_email",
                 condition=Q(verified=True))
```

Django's MySQL/MariaDB backend has `supports_partial_indexes = False`. Django
skips conditional unique constraints there and only reports system-check
warning `models.W036`. When OLDP moved from allauth 0.37 to 65.x, the old
unique index was dropped and no replacement was created. Production had no
unique index on email addresses at all.

### Root cause 2: checks only on signup

allauth's signup form refuses a second account for a known address. With
enumeration prevention it creates no account and mails the owner an "Account
Already Exists" notice. Social signup behaves the same way. The other entry
points did no check:

| Entry point | Behaviour before the fix |
|---|---|
| "Add email" on `/accounts/email/` | With `PREVENT_ENUMERATION`, an address used by another account was accepted silently. If that account had not verified it, the second user could confirm it, make it primary, and so copy it into `auth_user.email`. |
| Django admin (`UserAdmin`) | Stock forms accept any address. |
| `create_user`, `createsuperuser`, shell, fixtures | No check. |
| Upper/lower case | Django's `normalize_email` lowercases only the domain, and allauth looks `auth_user.email` up with an exact `=`. `Mixed@x` and `mixed@x` counted as different addresses on SQLite/Postgres. MariaDB's `_ci` collation hid this in production. |

### Reproduction (before the fix)

1. User A signs up with `x@example.com` and never confirms it.
2. User B logs in, opens `/accounts/email/` and adds `x@example.com`. No error.
3. B clicks the confirmation link and makes the address primary.
4. A and B now both have `auth_user.email = x@example.com`.

Admin: create or edit a user and give them an existing user's address. The
admin saves it.

### Impact

- A password reset for a shared address sends one reset mail per account. The
  person who controls the mailbox can reset all of them, including accounts
  that are not theirs.
- Inactivity warnings and newsletter mails go out once per account, so one
  person can get several.
- GDPR requests by email become ambiguous, and `user_stats` counts are
  inflated.

### Related bug: unconfirmed claims of an address

allauth treats an address as belonging to an account as soon as the account
*adds* it, before it is confirmed. Say Bob adds `x@example.com` to his account
and never confirms it, because of a typo or before the add-email check
existed. Then the real owner of `x@example.com`:

- cannot sign up. They get an "Account Already Exists" mail instead of a
  confirmation.
- gets a **password reset link for Bob's account** when they ask for a reset
  of `x@example.com`, and can take Bob's account over with it.

This also happens without any duplicate, because one unconfirmed claim is
enough.

### Related bug: failed sends reported as sent

Some users reported that no confirmation email arrived. When the SMTP relay
rejected a message or could not be reached, `CustomAccountAdapter.send_mail`
logged the error and was meant to show "Unable to send verification email".
The message never appeared, for two reasons:

- The handler looked for the request in the mail context, which allauth does
  not pass, so no error message was added.
- allauth then added its own "Confirmation email sent" message. The user saw
  "We have sent an e-mail to you for verification", and the account pages do
  not render messages anyway.

Every failed send therefore looked like a success to the user. The only trace
is in the log: `SMTP server rejected email to …`, `Failed to send email to …`
or `Unexpected error sending email to …`. Search the production logs for
these lines to see how often it happened.

Other reasons a user may see no confirmation mail, which work as intended:

- Signing up again with an address that already belongs to an account sends
  "Account Already Exists" instead. The mail contains a password reset link.
- allauth sends a new confirmation to the same address at most every
  3 minutes and skips extra ones silently. The earlier link stays valid.
- Links expire after 3 days. Logging in sends a new one.
- Social logins (GitHub, Google) get no confirmation mail by design.
- Spam filtering at the receiving end.

## The fix

An address is *taken* when another account has it as `auth_user.email` or as
a **verified** allauth `EmailAddress`. Other accounts' unverified secondary
addresses do not count: they are unproven claims, and counting them would let
anyone block an address. The rule lives in
`oldp/apps/accounts/email_uniqueness.py` and is enforced here:

| Layer | Change |
|---|---|
| Database | Migration `accounts.0015_unique_email_indexes` adds case-insensitive unique indexes. `auth_user`: one account per non-blank address (blank stays allowed, anonymized accounts have `email = ""`). `account_emailaddress`: one account per verified address. MariaDB/MySQL gets hidden stored generated columns `auth_user.oldp_email_ci` and `account_emailaddress.oldp_verified_email_ci`, each with a `UNIQUE` key. SQLite/PostgreSQL get partial indexes on `LOWER(email)`. |
| Add email | `ACCOUNT_FORMS["add_email"]` → `UniqueAddEmailForm` refuses taken addresses with "A user is already registered with this email address." |
| Confirm email | `CustomAccountAdapter.confirm_email` refuses to confirm a taken address (covers rows added before the fix). |
| Admin | `UserAdmin` forms reject taken addresses, and the add form now has an email field. |
| Normalization | A `pre_save` signal stores `User.email` lowercased. |
| Signup | `ACCOUNT_FORMS["signup"]` → `UniqueSignupForm` ignores other accounts' unconfirmed claims, so the real owner can sign up. For an address another account holds, allauth's behaviour stays: no account, "Account Already Exists" mail. |
| Password reset | `ACCOUNT_FORMS["reset_password"]` → `HolderOnlyResetPasswordForm` only sends links for accounts that hold the address, never for an account that merely claimed it. |
| Settings | `ACCOUNT_UNIQUE_EMAIL = True` and `ACCOUNT_PREVENT_ENUMERATION = True` are now set explicitly. |
| Tooling | `manage.py find_duplicate_emails` lists shared addresses and unverified claims. `--delete-unverified-claims` deletes the claims. |

Failed sends (`oldp/apps/accounts/adapters.py`, `templates/account/`):

- The error message is now added to the request taken from allauth's own
  request context.
- allauth's "Confirmation email sent" message is dropped when sending failed.
- The verification page says the mail could not be sent
  (`?send_failed=1`).
- The account pages render messages.
- The German translations are in `oldp/locale/de/LC_MESSAGES/django.po`.

Tests: `oldp/apps/accounts/tests/test_email_uniqueness.py` and
`oldp/apps/accounts/tests/test_email_sending.py`.

## Deployment

The migration **refuses to run while duplicates exist**, because a unique index
cannot be built over duplicate rows. The error names
`find_duplicate_emails`. Clean up first, then migrate.

### Step 1: back up the database

At least `auth_user`, `account_emailaddress` and `socialaccount_socialaccount`:

```bash
mysqldump oldp auth_user account_emailaddress socialaccount_socialaccount \
  > users-before-unique-email.sql
```

### Step 2: deploy the code, but do not migrate yet

Pull the new code or image. The new code runs fine on the old schema. Until
the migration runs, the form checks are active but the database does not
enforce uniqueness yet.

### Step 3: list the duplicates

```bash
python manage.py find_duplicate_emails
```

Example output:

```
x@example.com
  - shared auth_user.email (blocks migration 0015)
    #12 alice | user.email | EmailAddress(unverified, primary) | joined=2024-02-01 | never logged in
    #87 bob | user.email | EmailAddress(verified, primary) | social=github | joined=2025-06-11 | last_login=2026-10-01

DUPLICATES_TOTAL=1
```

Kinds:

- `shared auth_user.email` and `verified on several accounts` block the
  migration and must be resolved.
- `auth_user.email of one account, verified address of another` does not
  block the migration (no index spans both tables), but should be resolved
  too.
- `unverified claim of an address another account holds` does not block the
  migration either. The claim can no longer be confirmed, and signup and
  password reset ignore it. Delete these rows in step 4.

### Step 4: resolve each address

For every address, pick the account to keep. Prefer, in this order:

1. The one with the verified address (it proved control of the mailbox).
2. The one with a social login, API tokens or MCP grants.
3. The one with the most recent `last_login`.

For each other account, either:

- **Delete it** when it is clearly abandoned (unverified, never logged in,
  no tokens). `purge_unverified_users` deletes such signups after their grace
  period anyway. Use `python manage.py purge_unverified_users --dry-run` to
  see if it qualifies, or delete it in the admin.
- **Release the address** when the account is in use. This removes the
  address from that account, which keeps its username, password and data.
  Its owner can add a new address later. Consider telling them first.

Release an address in `python manage.py shell`:

```python
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User

def release(user_id, email):
    """Remove ``email`` from account ``user_id`` (keeps the account)."""
    user = User.objects.get(pk=user_id)
    EmailAddress.objects.filter(user=user, email__iexact=email).delete()
    if user.email.lower() == email.lower():
        user.email = ""
        user.save(update_fields=["email"])

release(12, "x@example.com")
```

When one person really owns several accounts, ask which one to keep and
handle the rest as above. There is no automatic account merge.

Delete all unverified claims in one go. Each deleted row is printed. Only
unconfirmed, non-primary addresses that another account holds are deleted,
and no account loses its own login address:

```bash
python manage.py find_duplicate_emails --delete-unverified-claims
```

Repeat until the command reports `DUPLICATES_TOTAL=0`:

```bash
python manage.py find_duplicate_emails --check   # exits 1 while any remain
```

### Step 5: migrate

```bash
python manage.py migrate accounts
```

On MariaDB this runs two `ALTER TABLE` statements that add a stored column and
rebuild `auth_user` and `account_emailaddress`. These tables are small, so
expect seconds, not minutes. If new duplicates appeared between step 4 and
now (signups keep running), the migration stops with the same error. Repeat
step 4 and migrate again.

The whole procedure (refusal, cleanup, migration, rollback) was tested on
MariaDB 10.11. Verify:

```sql
SHOW INDEX FROM auth_user WHERE Key_name = 'auth_user_email_ci_uniq';
SHOW INDEX FROM account_emailaddress
  WHERE Key_name = 'account_emailaddress_verified_email_ci_uniq';
```

### Step 6: restart

Restart the application server as usual.

### Rollback

`python manage.py migrate accounts 0014` drops the indexes and generated
columns. The data cleanup from step 4 is not undone. Restore the step 1
backup if needed.

### Notes

- `manage.py check` still shows allauth's `models.W036` warning on MariaDB.
  It is expected: migration 0015 replaces the constraint that the warning is
  about.
- The generated columns are invisible to Django. Raw `INSERT`s that list
  columns explicitly are unaffected. A raw `INSERT … VALUES` without a column
  list would have to skip them. `mysqldump` handles generated columns.
