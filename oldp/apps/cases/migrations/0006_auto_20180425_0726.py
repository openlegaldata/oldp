# Generated by Django 2.0.4 on 2018-04-25 07:26

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0005_auto_20180424_0849"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="case",
            name="from_juris",
        ),
        migrations.AddField(
            model_name="case",
            name="private",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Private content is hidden in production for non-staff users",
            ),
        ),
    ]
