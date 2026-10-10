# Newsletter consent

Open Legal Data may send project news by e-mail only with the user's prior,
double-opt-in confirmed consent (UWG § 7 Abs. 2 Nr. 2, Art. 6 Abs. 1 lit. a
DSGVO). No bulk mailing exists in the code yet; this page describes how the
consent and its proof are stored so that mailings, once sent, can be justified
(Art. 7 Abs. 1 DSGVO puts the burden of proof on the sender).

## Fields on `UserProfile`

| Field | Meaning |
|---|---|
| `newsletter_opt_in` | live flag: the user asked for mail (not yet a valid consent) |
| `newsletter_doi_confirmed_at` | double-opt-in link clicked; `is_newsletter_subscriber` requires both |
| `newsletter_opt_in_at`, `consent_source` | when and where (signup, on-login prompt, dashboard) the box was ticked |
| `newsletter_consent_text` | the exact wording the user saw, see below |
| `newsletter_unsubscribed_at` | when the consent was withdrawn |

**Unsubscribing clears only the live flag** and stamps `newsletter_unsubscribed_at`;
the other fields stay as proof. The proof lives and dies with the account:
self-service deletion and the inactivity anonymisation remove it. A new opt-in
after an unsubscribe resets confirmation and withdrawal, so a new double
opt-in is required and the latest consent is the one that counts.

## Versioned consent wording: `NewsletterConsentText`

The checkbox label (signup form, on-login prompt, dashboard) and the quote in
the confirmation e-mail are rendered from the newest `NewsletterConsentText`
row for the active language, and `record_opt_in()` stores that same row on the
profile. What was shown and what was recorded are therefore the same object.

The table is **append-only and migration-only**:

- rows are created solely by data migrations (`0014_newsletter_consent_text_data`
  is the seed; copy its pattern), so every wording change is reviewed in git and
  logged with the deploy;
- the admin lists the rows but has no add, change or delete;
- `save()` refuses to update an existing row and `delete()` raises;
- the profile FK is `PROTECT`, so a row in use can never be removed.

To change the wording, add a migration that inserts a new `version` (date
label, e.g. `2027-03`) in every language the site renders. Never edit an old
row: profiles point at it. The seed contains `2026-06` (the original English
sentence, which all users saw because the German translation was missing) and
`2026-10` in English and German; existing opt-ins were backfilled to `2026-06`.

The privacy policy served at `/pages/privacy/` (deployment repo) describes this
behaviour in its "Newsletter" section; keep both in sync.
