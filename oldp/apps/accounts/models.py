import binascii
import os
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class APIToken(models.Model):
    """
    API Token model that supports multiple tokens per user with enhanced features.

    This model replaces the default DRF Token model with a more feature-rich implementation
    that supports:
    - Multiple tokens per user
    - Named tokens for easy identification
    - Token expiration
    - Usage tracking
    - Active/inactive status
    - Optional scope restrictions
    """

    # Core fields
    key = models.CharField(
        _("Key"),
        max_length=40,
        unique=True,
        db_index=True,
        help_text=_("The API token key")
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="api_tokens",
        on_delete=models.CASCADE,
        verbose_name=_("User"),
        help_text=_("The user this token belongs to")
    )
    name = models.CharField(
        _("Name"),
        max_length=100,
        help_text=_("A descriptive name for this token (e.g., 'Production Server', 'CI/CD Pipeline')")
    )

    # Timestamp fields
    created = models.DateTimeField(
        _("Created"),
        auto_now_add=True,
        help_text=_("When this token was created")
    )
    last_used = models.DateTimeField(
        _("Last used"),
        null=True,
        blank=True,
        help_text=_("When this token was last used")
    )
    expires_at = models.DateTimeField(
        _("Expires at"),
        null=True,
        blank=True,
        help_text=_("When this token expires (null = never expires)")
    )

    # Status and permissions
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        help_text=_("Whether this token is currently active")
    )
    scopes = models.JSONField(
        _("Scopes"),
        default=list,
        blank=True,
        help_text=_("List of scopes this token has access to (e.g., ['read', 'write'])")
    )

    class Meta:
        verbose_name = _("API Token")
        verbose_name_plural = _("API Tokens")
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @classmethod
    def generate_key(cls):
        """Generate a random API key"""
        return binascii.hexlify(os.urandom(20)).decode()

    def is_expired(self):
        """Check if the token has expired"""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    def is_valid(self):
        """Check if the token is valid (active and not expired)"""
        return self.is_active and not self.is_expired()

    def has_scope(self, scope):
        """Check if the token has a specific scope"""
        if not self.scopes:
            return True  # No scopes means full access
        return scope in self.scopes

    def mark_used(self):
        """Update the last_used timestamp"""
        self.last_used = timezone.now()
        self.save(update_fields=["last_used"])
