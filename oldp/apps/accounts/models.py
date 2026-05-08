import binascii
import os

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class APITokenPermission(models.Model):
    """Individual permission for API tokens.

    Defines granular access control for specific resources and actions.
    Format: <resource>:<action> (e.g., "cases:read", "laws:write")
    """

    RESOURCE_CHOICES = [
        ("cases", _("Cases")),
        ("laws", _("Laws")),
        ("courts", _("Courts")),
        ("lawbooks", _("Law Books")),
        ("references", _("References")),
        ("annotations", _("Annotations")),
    ]

    ACTION_CHOICES = [
        ("read", _("Read")),
        ("write", _("Write")),
        ("delete", _("Delete")),
    ]

    resource = models.CharField(
        _("Resource"),
        max_length=50,
        choices=RESOURCE_CHOICES,
        help_text=_("The resource this permission applies to"),
    )
    action = models.CharField(
        _("Action"),
        max_length=20,
        choices=ACTION_CHOICES,
        help_text=_("The action allowed on this resource"),
    )
    description = models.TextField(
        _("Description"),
        blank=True,
        help_text=_("Optional description of what this permission allows"),
    )

    class Meta:
        verbose_name = _("API Token Permission")
        verbose_name_plural = _("API Token Permissions")
        unique_together = [["resource", "action"]]
        ordering = ["resource", "action"]

    def __str__(self):
        return f"{self.resource}:{self.action}"

    def get_permission_string(self):
        """Get the permission as a string in format resource:action"""
        return f"{self.resource}:{self.action}"


class APITokenPermissionGroup(models.Model):
    """Group of permissions that can be assigned to API tokens.

    This allows administrators to create reusable permission sets
    (e.g., "read_only", "full_access", "default").
    """

    name = models.CharField(
        _("Name"),
        max_length=100,
        unique=True,
        help_text=_("Unique name for this permission group"),
    )
    description = models.TextField(
        _("Description"),
        blank=True,
        help_text=_("Description of what this permission group allows"),
    )
    permissions = models.ManyToManyField(
        APITokenPermission,
        related_name="permission_groups",
        verbose_name=_("Permissions"),
        blank=True,
        help_text=_("Permissions included in this group"),
    )
    is_default = models.BooleanField(
        _("Is Default"),
        default=False,
        help_text=_("Whether this is the default permission group for new tokens"),
    )
    created = models.DateTimeField(_("Created"), auto_now_add=True)
    updated = models.DateTimeField(_("Updated"), auto_now=True)

    class Meta:
        verbose_name = _("API Token Permission Group")
        verbose_name_plural = _("API Token Permission Groups")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def has_permission(self, resource, action):
        """Check if this group has a specific permission"""
        return self.permissions.filter(resource=resource, action=action).exists()

    def get_permission_list(self):
        """Get all permissions as a list of strings"""
        return [p.get_permission_string() for p in self.permissions.all()]


class APIToken(models.Model):
    """API Token model that supports multiple tokens per user with enhanced features.

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
        help_text=_("The API token key"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="api_tokens",
        on_delete=models.CASCADE,
        verbose_name=_("User"),
        help_text=_("The user this token belongs to"),
    )
    name = models.CharField(
        _("Name"),
        max_length=100,
        help_text=_(
            "A descriptive name for this token (e.g., 'Production Server', 'CI/CD Pipeline')"
        ),
    )

    # Timestamp fields
    created = models.DateTimeField(
        _("Created"), auto_now_add=True, help_text=_("When this token was created")
    )
    last_used = models.DateTimeField(
        _("Last used"),
        null=True,
        blank=True,
        help_text=_("When this token was last used"),
    )
    expires_at = models.DateTimeField(
        _("Expires at"),
        null=True,
        blank=True,
        help_text=_("When this token expires (null = never expires)"),
    )

    # Status and permissions
    is_active = models.BooleanField(
        _("Active"), default=True, help_text=_("Whether this token is currently active")
    )
    permission_group = models.ForeignKey(
        "APITokenPermissionGroup",
        related_name="tokens",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Permission Group"),
        help_text=_(
            "The permission group assigned to this token (defines what resources it can access)"
        ),
    )
    scopes = models.JSONField(
        _("Scopes"),
        default=list,
        blank=True,
        help_text=_(
            "Deprecated: Use permission_group instead. List of scopes this token has access to"
        ),
    )
    rate_limit = models.PositiveIntegerField(
        _("Rate Limit"),
        null=True,
        blank=True,
        help_text=_(
            "Custom rate limit in requests per hour for this token. "
            "Leave blank to use the default rate."
        ),
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
        """Check if the token has a specific scope (deprecated method).
        Use has_permission() instead.
        """
        if not self.scopes:
            return True  # No scopes means full access
        return scope in self.scopes

    def has_permission(self, resource, action):
        """Check if the token has permission for a specific resource and action.

        Resolution order:
        1. The token's assigned ``permission_group``.
        2. Legacy ``scopes`` (deprecated; kept for tokens issued before
           permission groups existed).
        3. The system-wide default group (``is_default=True``) — used for
           tokens with neither a group nor scopes.
        4. Deny.

        The previous fallback was to grant full access when neither a group
        nor scopes were set. That made every newly created token an
        unrestricted write token, which is unsafe by default.

        Args:
            resource: The resource name (e.g., "cases", "laws")
            action: The action name (e.g., "read", "write", "delete")

        Returns:
            bool: True if the token has the permission, False otherwise
        """
        if self.permission_group:
            return self.permission_group.has_permission(resource, action)

        if self.scopes:
            permission_string = f"{resource}:{action}"
            return (
                permission_string in self.scopes
                or resource in self.scopes
                or action in self.scopes
            )

        default_group = APITokenPermissionGroup.objects.filter(is_default=True).first()
        if default_group is not None:
            return default_group.has_permission(resource, action)

        return False

    def get_permissions(self):
        """Get all permissions this token has as a list of strings."""
        if self.permission_group:
            return self.permission_group.get_permission_list()
        if self.scopes:
            return list(self.scopes)
        default_group = APITokenPermissionGroup.objects.filter(is_default=True).first()
        if default_group is not None:
            return default_group.get_permission_list()
        return []

    def get_rate_limit(self):
        """Get the custom rate limit for this token, or None for default."""
        return self.rate_limit

    def mark_used(self):
        """Update the last_used timestamp"""
        self.last_used = timezone.now()
        self.save(update_fields=["last_used"])
