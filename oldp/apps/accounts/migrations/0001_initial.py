# Generated migration for APIToken model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='APIToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(db_index=True, help_text='The API token key', max_length=40, unique=True, verbose_name='Key')),
                ('name', models.CharField(help_text="A descriptive name for this token (e.g., 'Production Server', 'CI/CD Pipeline')", max_length=100, verbose_name='Name')),
                ('created', models.DateTimeField(auto_now_add=True, help_text='When this token was created', verbose_name='Created')),
                ('last_used', models.DateTimeField(blank=True, help_text='When this token was last used', null=True, verbose_name='Last used')),
                ('expires_at', models.DateTimeField(blank=True, help_text='When this token expires (null = never expires)', null=True, verbose_name='Expires at')),
                ('is_active', models.BooleanField(default=True, help_text='Whether this token is currently active', verbose_name='Active')),
                ('scopes', models.JSONField(blank=True, default=list, help_text="List of scopes this token has access to (e.g., ['read', 'write'])", verbose_name='Scopes')),
                ('user', models.ForeignKey(help_text='The user this token belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='api_tokens', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'API Token',
                'verbose_name_plural': 'API Tokens',
                'ordering': ['-created'],
            },
        ),
        migrations.AddIndex(
            model_name='apitoken',
            index=models.Index(fields=['user', 'is_active'], name='accounts_ap_user_id_ac6ac5_idx'),
        ),
        migrations.AddIndex(
            model_name='apitoken',
            index=models.Index(fields=['expires_at'], name='accounts_ap_expires_e66c1e_idx'),
        ),
    ]
