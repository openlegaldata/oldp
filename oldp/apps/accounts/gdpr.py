"""DSGVO/GDPR self-service: data export (Art. 15/20) and erasure (Art. 17).

``build_export_zip`` packages everything we store *about* a user into a ZIP the
user can download from their dashboard. ``delete_user_account`` permanently
deletes the account.

Erasure note: token-created content (cases/laws/courts/law books) is **kept** —
``created_by_token`` is ``SET_NULL`` on delete, so deleting the user (which
cascades the tokens) leaves the public legal content intact, just unattributed.
"""

import io
import json
import zipfile

from django.utils import timezone


def _mask_key(key):
    """Mask a token/key so the export shows which token it is without leaking it."""
    if not key:
        return ""
    if len(key) <= 8:
        return "…"
    return f"{key[:4]}…{key[-4:]}"


def _content_summary(user):
    """Counts of content this user submitted via the API (kept after deletion)."""
    summary = {}
    try:
        from oldp.apps.cases.models import Case
        from oldp.apps.courts.models import Court
        from oldp.apps.laws.models import Law, LawBook

        summary = {
            "cases": Case.objects.filter(created_by_token__user=user).count(),
            "laws": Law.objects.filter(created_by_token__user=user).count(),
            "law_books": LawBook.objects.filter(created_by_token__user=user).count(),
            "courts": Court.objects.filter(created_by_token__user=user).count(),
        }
    except Exception:  # noqa: BLE001 — never let a content query break the export
        summary = {}
    return summary


def build_export_payload(user):
    """Return a JSON-serializable dict of the user's personal data."""
    from allauth.account.models import EmailAddress
    from allauth.socialaccount.models import SocialAccount
    from rest_framework.authtoken.models import Token

    from oldp.apps.accounts.models import APIToken

    profile = getattr(user, "profile", None)

    account = {
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        "is_active": user.is_active,
    }

    profile_data = None
    if profile is not None:
        profile_data = {
            "display_name": profile.display_name,
            "organization": profile.organization,
            "role": profile.role,
            "use_case": profile.use_case,
            "country": profile.country,
            "newsletter_opt_in": profile.newsletter_opt_in,
            "newsletter_opt_in_at": profile.newsletter_opt_in_at,
            "newsletter_doi_confirmed_at": profile.newsletter_doi_confirmed_at,
            "consent_source": profile.consent_source,
            "max_api_tokens": profile.max_api_tokens,
            "created": profile.created,
            "updated": profile.updated,
        }

    email_addresses = [
        {"email": e.email, "verified": e.verified, "primary": e.primary}
        for e in EmailAddress.objects.filter(user=user)
    ]

    social_accounts = [
        {
            "provider": s.provider,
            "uid": s.uid,
            "date_joined": s.date_joined,
            "last_login": s.last_login,
            "extra_data": s.extra_data,
        }
        for s in SocialAccount.objects.filter(user=user)
    ]

    api_tokens = [
        {
            "name": t.name,
            "key_masked": _mask_key(t.key),
            "created": t.created,
            "last_used": t.last_used,
            "expires_at": t.expires_at,
            "is_active": t.is_active,
            "rate_limit": t.rate_limit,
            "permission_group": (
                t.permission_group.name if t.permission_group else None
            ),
        }
        for t in APIToken.objects.filter(user=user)
    ]

    personal_token = None
    legacy = Token.objects.filter(user=user).first()
    if legacy is not None:
        personal_token = {
            "key_masked": _mask_key(legacy.key),
            "created": legacy.created,
        }

    return {
        "export_generated_at": timezone.now(),
        "account": account,
        "profile": profile_data,
        "email_addresses": email_addresses,
        "social_accounts": social_accounts,
        "api_tokens": api_tokens,
        "personal_token": personal_token,
        "content_submitted_via_api": _content_summary(user),
    }


def _readme(user):
    """Bilingual (DE/EN) explanation shipped inside the ZIP."""
    return f"""Open Legal Data — Datenexport für {user.username}

Diese ZIP-Datei enthält die personenbezogenen Daten, die wir zu deinem Konto
gespeichert haben (DSGVO Art. 15/20).

- account.json: dein Konto, Profil, E-Mail-Adressen, verknüpfte Login-Konten
  und die Metadaten deiner API-Tokens (Token-Schlüssel sind aus
  Sicherheitsgründen maskiert).
- content_submitted_via_api: Anzahl der von dir über die API eingereichten
  Inhalte (Urteile, Gesetze, Gerichte). Diese Inhalte sind öffentliche
  Rechtsdaten und bleiben auch nach einer Kontolöschung erhalten.

Fragen? Kontaktiere uns über das Kontaktformular auf der Website.

--------------------------------------------------------------------------------

Open Legal Data — data export for {user.username}

This ZIP contains the personal data we hold about your account (GDPR Art. 15/20).

- account.json: your account, profile, email addresses, connected login
  accounts and the metadata of your API tokens (token secrets are masked for
  security).
- content_submitted_via_api: counts of content you submitted via the API
  (cases, laws, courts). This content is public legal data and is retained even
  after account deletion.

Questions? Reach us via the contact form on the website.
"""


def build_export_zip(user):
    """Return the bytes of a ZIP archive containing the user's data export."""
    payload = build_export_payload(user)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", _readme(user))
        zf.writestr(
            "account.json",
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
    buffer.seek(0)
    return buffer.getvalue()


def delete_user_account(user):
    """Permanently delete the account.

    Cascades to the user's tokens, email addresses, social accounts and profile.
    Token-created content survives because ``created_by_token`` is ``SET_NULL``.
    """
    user.delete()
