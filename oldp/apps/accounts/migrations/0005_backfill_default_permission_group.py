"""Backfill ``permission_group`` for existing tokens.

Before this migration, ``APIToken.has_permission`` returned ``True`` for any
(resource, action) when a token had neither a permission group nor any
legacy scopes — i.e. every newly created token had unrestricted write access.

That permissive fallback is being replaced (in ``models.py``) with one that
honours the ``is_default=True`` group instead. To keep behaviour predictable
for tokens that already exist in the wild, this migration assigns each such
token to that default group explicitly. Tokens that already have a
permission group or non-empty legacy scopes are left untouched.
"""

from django.db import migrations


def backfill_default_group(apps, schema_editor):
    APIToken = apps.get_model("accounts", "APIToken")
    APITokenPermissionGroup = apps.get_model("accounts", "APITokenPermissionGroup")

    default_group = APITokenPermissionGroup.objects.filter(is_default=True).first()
    if default_group is None:
        # No default group has been configured yet — nothing to backfill.
        # ``models.py`` will deny access for these tokens until an admin
        # sets ``is_default=True`` on a group.
        return

    APIToken.objects.filter(permission_group__isnull=True).update(
        permission_group=default_group
    )


def reverse_noop(apps, schema_editor):
    """Reversal is a no-op: we cannot tell which tokens were originally
    NULL versus which had been explicitly assigned to the default group.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_apitoken_rate_limit"),
    ]

    operations = [
        migrations.RunPython(backfill_default_group, reverse_noop),
    ]
