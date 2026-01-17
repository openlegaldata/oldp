# Generated manually for case creation API

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_apitokenpermission_apitokenpermissiongroup_and_more'),
        ('cases', '0021_remove_old_source_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='case',
            name='created_by_token',
            field=models.ForeignKey(
                blank=True,
                help_text='API token used to create this case via the API',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_cases',
                to='accounts.apitoken',
            ),
        ),
    ]
