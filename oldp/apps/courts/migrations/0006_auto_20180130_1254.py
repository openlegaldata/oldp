# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2018-01-30 12:54
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("courts", "0005_auto_20171207_0947"),
    ]

    operations = [
        migrations.AddField(
            model_name="court",
            name="slug",
            field=models.SlugField(
                default="", help_text="Code as lowercase", max_length=20
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="state",
            name="slug",
            field=models.SlugField(default="", help_text="Name field as slug"),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="court",
            name="city",
            field=models.ForeignKey(
                help_text="Court belongs to this city, if null court is state-level",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="courts.City",
            ),
        ),
        migrations.AlterField(
            model_name="court",
            name="code",
            field=models.CharField(
                help_text="Unique court identifier based on ECLI (e.g. BVerfG)",
                max_length=20,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="court",
            name="court_type",
            field=models.CharField(
                help_text="Court type AG,VG,...", max_length=10, null=True
            ),
        ),
        migrations.AlterField(
            model_name="court",
            name="name",
            field=models.CharField(
                help_text="Full name of the court with location", max_length=100
            ),
        ),
        migrations.AlterField(
            model_name="court",
            name="state",
            field=models.ForeignKey(
                help_text="Court belongs to this state (derive country of this field)",
                on_delete=django.db.models.deletion.CASCADE,
                to="courts.State",
            ),
        ),
        migrations.AlterField(
            model_name="court",
            name="updated",
            field=models.DateTimeField(
                auto_now=True, help_text="Holds date time of last db update"
            ),
        ),
        migrations.AlterField(
            model_name="state",
            name="name",
            field=models.CharField(max_length=50),
        ),
    ]
