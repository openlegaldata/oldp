import logging

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Load dummy users (admin and regular user) for testing"

    def handle(self, *args, **options):
        # Check if users already exist
        admin_exists = User.objects.filter(username="admin").exists()
        user_exists = User.objects.filter(username="user").exists()

        if admin_exists or user_exists:
            raise CommandError(
                "Dummy users already exist. Please delete them first if you want to reload."
            )

        # Create admin user
        admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="admin"
        )
        # Get or create and verify email address for admin
        admin_email, created = EmailAddress.objects.get_or_create(
            user=admin,
            email="admin@example.com",
            defaults={"verified": True, "primary": True},
        )
        if not created:
            admin_email.verified = True
            admin_email.primary = True
            admin_email.save()
        logger.info("Created admin user (username: admin, password: admin)")

        # Create regular user
        user = User.objects.create_user(
            username="user", email="user@example.com", password="user"
        )
        # Get or create and verify email address for user
        user_email, created = EmailAddress.objects.get_or_create(
            user=user,
            email="user@example.com",
            defaults={"verified": True, "primary": True},
        )
        if not created:
            user_email.verified = True
            user_email.primary = True
            user_email.save()
        logger.info("Created user (username: user, password: user)")

        logger.info("Dummy users loaded successfully")
