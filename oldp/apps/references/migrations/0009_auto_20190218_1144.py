# Generated by Django 2.1.2 on 2019-02-18 11:44

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0008_remove_uuid__change_line_to_int"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reference",
            name="case",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="cases.Case",
            ),
        ),
        migrations.AlterField(
            model_name="reference",
            name="law",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="laws.Law",
            ),
        ),
    ]
