from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance=None, created=False, **kwargs):
    """Ensure every user has a UserProfile.

    Uses ``get_or_create`` so it is idempotent and safe for users that predate
    the profile model.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)
