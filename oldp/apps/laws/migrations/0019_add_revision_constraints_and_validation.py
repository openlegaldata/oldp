# Generated manually for revision validation and constraints

from django.db import migrations, models
import django.db.models.deletion
import oldp.apps.laws.models


class Migration(migrations.Migration):

    dependencies = [
        ('laws', '0018_auto_20181128_1059'),
    ]

    operations = [
        # Add validator to revision_date field
        migrations.AlterField(
            model_name='lawbook',
            name='revision_date',
            field=models.DateField(
                default='1990-01-01',
                help_text='Date of revision',
                validators=[oldp.apps.laws.models.validate_revision_date]
            ),
        ),
        # Add unique constraint for latest=True per code
        migrations.AddConstraint(
            model_name='lawbook',
            constraint=models.UniqueConstraint(
                condition=models.Q(latest=True),
                fields=['code'],
                name='unique_latest_per_code'
            ),
        ),
    ]
