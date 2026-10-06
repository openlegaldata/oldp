# Newsletter consent and its evidence log

Open Legal Data sends project news by e-mail only with the user's prior,
double-opt-in confirmed consent (UWG § 7 Abs. 2 Nr. 2, Art. 6 Abs. 1 lit. a
DSGVO). Two things are stored, deliberately apart:

| | Where | Purpose | Lifetime |
|---|---|---|---|
| **Live subscription state** | `UserProfile.newsletter_*`, `consent_source` | decides whether mail may be sent (`is_newsletter_subscriber`) | cleared immediately on unsubscribe, anonymisation or deletion |
| **Evidence trail** | `NewsletterConsentLog` (one row per event) | proves *that*, *when*, *where* and *to which wording* the user consented, so mailings already sent can be justified | 3 years after the end of the year of revocation, then purged |

## What is logged

| Event | Trigger | Row |
|---|---|---|
| `opt_in` | checkbox ticked on signup, on-login prompt or dashboard | e-mail, source, `consent_text` (the checkbox wording in the user's language), `consent_text_version` |
| `confirmed` | double-opt-in link clicked (`newsletter_confirm_view`) | same, once per confirmation |
| `revoked` | dashboard unsubscribe, inactivity anonymisation (`lifecycle.anonymize_user`), account deletion (`gdpr.delete_user_account`) | e-mail and source only |

The wording lives in one place, `CONSENT_TEXT` / `CONSENT_TEXT_VERSION` in
`oldp/apps/accounts/newsletter.py`. Bump the version whenever the checkbox
text or the confirmation e-mail changes in substance; old rows keep the old
version string and text.

Rows are append-only: the admin (`Accounts › Newsletter consent log`) is
read-only and the only deletion path is the retention purge. `user` is a
`SET_NULL` foreign key, so rows survive account deletion with the e-mail
address copied at logging time. The data export (`/accounts/data-export/`)
includes the user's rows.

## Retention purge

```bash
manage.py purge_newsletter_consent_logs            # delete expired chains
manage.py purge_newsletter_consent_logs --dry-run  # report only
```

A "chain" is every row for the same user or e-mail address up to and including
a `revoked` row. The chain is deleted once the revocation is older than three
full calendar years (revoked in 2026 → deleted from 1 January 2030). Rows
written after a later re-subscription are untouched. The deployment runs this
weekly (`cronjob-weekly.sh` in the deployment repo).

This implements the "Newsletter" section of the privacy policy served at
`/pages/privacy/`; keep both in sync.
