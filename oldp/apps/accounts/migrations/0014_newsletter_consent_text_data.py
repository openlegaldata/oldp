"""Seed the newsletter consent texts and backfill existing opt-ins.

NewsletterConsentText rows are created ONLY by data migrations like this one
(see the model docstring). To introduce new wording: add a new migration that
inserts a new ``version`` (never edit an existing row), in every language the
site renders. The newest version per language becomes the current text.

Versions:

* ``2026-06`` — the wording shipped with the account feature (oldp v0.12.0,
  June 2026): "Send me occasional product updates and news by email. I can
  unsubscribe at any time." The German translation was missing in the .po
  file, so every user — including those on the German site — saw the English
  sentence. Hence only an ``en`` row exists for this version and all profiles
  that opted in before this migration are pointed at it.
* ``2026-10`` — the wording introduced after the legal review of the privacy
  policy (names the sender, the content and how to withdraw), in ``en`` and
  ``de``.
"""

from django.db import migrations

TEXTS = [
    (
        "2026-06",
        "en",
        "Send me occasional product updates and news by email. "
        "I can unsubscribe at any time.",
    ),
    (
        "2026-10",
        "en",
        "I would like to receive news from Open Legal Data by e-mail (new datasets, "
        "features, events). I can withdraw this consent at any time in my account "
        "or by e-mail to hello@openlegaldata.io.",
    ),
    (
        "2026-10",
        "de",
        "Ich möchte per E-Mail Neuigkeiten von Open Legal Data erhalten (neue "
        "Datensätze, Funktionen, Veranstaltungen). Ich kann diese Einwilligung "
        "jederzeit in meinem Konto oder per E-Mail an hello@openlegaldata.io "
        "widerrufen.",
    ),
]


def seed(apps, schema_editor):
    NewsletterConsentText = apps.get_model("accounts", "NewsletterConsentText")
    UserProfile = apps.get_model("accounts", "UserProfile")

    rows = {}
    for version, language, text in TEXTS:
        rows[(version, language)], _ = NewsletterConsentText.objects.get_or_create(
            version=version, language=language, defaults={"text": text}
        )

    # Existing opt-ins (confirmed or pending) saw the 2026-06 English wording.
    UserProfile.objects.filter(
        newsletter_opt_in_at__isnull=False, newsletter_consent_text__isnull=True
    ).update(newsletter_consent_text=rows[("2026-06", "en")])


def unseed(apps, schema_editor):
    NewsletterConsentText = apps.get_model("accounts", "NewsletterConsentText")
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.update(newsletter_consent_text=None)
    # Bypass the model's append-only delete() (historical models don't carry
    # custom methods anyway); reversing the seed is the one legitimate case.
    NewsletterConsentText.objects.filter(version__in={v for v, _, _ in TEXTS}).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_newsletter_consent_text"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
