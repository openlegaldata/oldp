import logging

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.models import UserProfile

logger = logging.getLogger(__name__)


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


@receiver(user_logged_in)
def cancel_pending_deletion(sender, request, user, **kwargs):
    """Logging in rescues an account that was warned for inactivity.

    Fires for every login (local and social). Clears the deletion-warning
    timestamps so the next ``purge_inactive_users`` run leaves the account
    alone — this is what makes the warning email's "log in to keep your
    account" promise true. A deactivated account cannot log in, so this only
    rescues users during the warning grace window.
    """
    profile = getattr(user, "profile", None)
    if profile is None:
        return
    if profile.cancel_pending_deletion():
        profile.save(
            update_fields=[
                "deletion_warning_sent_at",
                "deletion_scheduled_for",
                "updated",
            ]
        )
        logger.info("Cancelled pending deletion for user %s on login", user.pk)
