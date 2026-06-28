from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    """Create a UserProfile for every existing user that lacks one.

    New users get a profile via the post_save signal; this backfills users that
    predate the model.
    """
    UserProfile = apps.get_model("accounts", "UserProfile")
    # Resolve the user model through the historical app registry.
    user_model = apps.get_model("auth", "User")

    existing = set(UserProfile.objects.values_list("user_id", flat=True))
    to_create = [
        UserProfile(user_id=uid)
        for uid in user_model.objects.exclude(id__in=existing).values_list(
            "id", flat=True
        )
    ]
    if to_create:
        UserProfile.objects.bulk_create(to_create, batch_size=500)


def noop_reverse(apps, schema_editor):
    # Reversing the schema migration drops the table; nothing to undo here.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_userprofile"),
    ]

    operations = [
        migrations.RunPython(create_missing_profiles, noop_reverse),
    ]
