# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-12-07 09:47
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("courts", "0004_court_updated"),
    ]

    operations = [
        migrations.AddField(
            model_name="court",
            name="wikipedia_title",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name="court",
            name="description",
            field=models.TextField(default=""),
        ),
    ]
