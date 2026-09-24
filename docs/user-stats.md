# User Statistics

`manage.py user_stats` prints aggregate statistics about user accounts for a
date range as JSON: signups, activation, logins, newsletter consent, profile
completeness and API/MCP adoption. It only reads, and it outputs counts, not
usernames, email addresses or ids.

```bash
python manage.py user_stats                                   # last 30 days
python manage.py user_stats --since 2026-09-01 --until 2026-09-30
python manage.py user_stats --days 7 --free-text              # plus profile texts
```

The internal-tools `/user-stats` skill runs it on prod, analyses the result
and emails the report.

## Definitions

Staff and superusers are left out of every number.

| Metric | Definition |
|---|---|
| Signup | `date_joined` is in the range. |
| Activated | The user has a verified email address (allauth `EmailAddress.verified`). Social signups arrive verified. |
| Funnel | Of the range's signups: verified → ever logged in → created an API token → used an API token → connected an MCP client (OAuth grant or token). |
| Login | `last_login` is in the range. OLDP keeps no login history, so this is a lower bound: a user who also logged in after the range is not counted. *Returning* users joined before the range. |
| Newsletter subscriber | Opted in **and** confirmed the double opt-in (`UserProfile.is_newsletter_subscriber`). |
| Complete profile | Role and use case are set (`UserProfile.is_profile_complete`). |
| Email category | `academic` (`.edu`, `.ac.<cc>`, `uni-`/`tu-`/`fh-`/… domains), `freemail` (a fixed list of mail providers), else `other`. |

Every range-scoped block is computed for the range (`current`) and for the
equally long range right before it (`previous`), so trends can be read off
directly. `totals` is the all-time state at the time of the run.

## Caveats

- `purge_unverified_users` deletes never-verified signups after a grace
  period. Older ranges therefore show fewer signups and a higher activation
  ratio than they had at the time; compare ranges of the same age.
- OAuth tokens expire and may be cleared, so the MCP numbers are a lower
  bound.

## Free text

`--free-text` adds a `free_text` list with the display name, organization and
use case of every user who signed up in the range, or completed their profile
in it. Each row carries only the role, country and email category besides the
text; `joined_in_range` tells the two groups apart. Use cases are cut at 1,000
characters.
