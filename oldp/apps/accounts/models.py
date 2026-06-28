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


class UserProfile(models.Model):
    """Extended profile data attached to a user.

    Stock Django ``User`` only stores username/email/password. This model
    carries the segmentation data we collect at signup (role / organization /
    use case) for community outreach, plus marketing-email consent state with a
    double-opt-in audit trail.

    One profile per user, created automatically by a ``post_save`` signal on
    the user model (see ``accounts.signals``).

    Consent note (UWG §7 / DSGVO): ``newsletter_opt_in`` being ``True`` is NOT
    sufficient to send marketing mail — the opt-in must be confirmed via
    double-opt-in (``newsletter_doi_confirmed_at`` set). Use
    ``is_newsletter_subscriber`` as the single source of truth.
    """

    ROLE_RESEARCHER = "researcher"
    ROLE_JOURNALIST = "journalist"
    ROLE_DEVELOPER = "developer"
    ROLE_LEGAL_TECH = "legal_tech"
    ROLE_LAWYER = "lawyer"
    ROLE_STUDENT = "student"
    ROLE_OTHER = "other"
    ROLE_CHOICES = [
        (ROLE_RESEARCHER, _("Researcher / Academia")),
        (ROLE_JOURNALIST, _("Journalist")),
        (ROLE_DEVELOPER, _("Developer")),
        (ROLE_LEGAL_TECH, _("Legal tech / Startup")),
        (ROLE_LAWYER, _("Lawyer / Legal professional")),
        (ROLE_STUDENT, _("Student")),
        (ROLE_OTHER, _("Other")),
    ]

    CONSENT_SOURCE_SIGNUP = "signup"
    CONSENT_SOURCE_PROMPT = "prompt"
    CONSENT_SOURCE_DASHBOARD = "dashboard"
    CONSENT_SOURCE_IMPORT = "import"
    CONSENT_SOURCE_CHOICES = [
        (CONSENT_SOURCE_SIGNUP, _("Signup form")),
        (CONSENT_SOURCE_PROMPT, _("On-login prompt")),
        (CONSENT_SOURCE_DASHBOARD, _("Dashboard")),
        (CONSENT_SOURCE_IMPORT, _("Imported")),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("User"),
    )

    # Segmentation / outreach data (all optional — never block signup on these)
    display_name = models.CharField(
        _("Display name"),
        max_length=150,
        blank=True,
        help_text=_("Optional public name; falls back to the username."),
    )
    organization = models.CharField(
        _("Organization"),
        max_length=200,
        blank=True,
        help_text=_("Company, university, or project (optional)."),
    )
    role = models.CharField(
        _("Role"),
        max_length=20,
        choices=ROLE_CHOICES,
        blank=True,
        help_text=_("How do you use Open Legal Data? (optional)"),
    )
    use_case = models.TextField(
        _("Use case"),
        blank=True,
        help_text=_("What are you building with Open Legal Data? (optional)"),
    )
    country = models.CharField(
        _("Country"),
        max_length=2,
        blank=True,
        help_text=_("ISO 3166-1 alpha-2 country code (optional)."),
    )

    # Marketing-email consent + double-opt-in audit trail
    newsletter_opt_in = models.BooleanField(
        _("Newsletter opt-in"),
        default=False,
        help_text=_(
            "User requested marketing email. Not a valid consent until confirmed."
        ),
    )
    newsletter_opt_in_at = models.DateTimeField(
        _("Opt-in requested at"),
        null=True,
        blank=True,
        help_text=_("When the opt-in checkbox/toggle was set."),
    )
    newsletter_doi_confirmed_at = models.DateTimeField(
        _("Double-opt-in confirmed at"),
        null=True,
        blank=True,
        help_text=_(
            "When the confirmation link was clicked. Required to send marketing mail."
        ),
    )
    consent_source = models.CharField(
        _("Consent source"),
        max_length=20,
        choices=CONSENT_SOURCE_CHOICES,
        blank=True,
        help_text=_("Where the opt-in was captured (audit)."),
    )

    # On-login enrichment prompt + incentive
    enrichment_prompted_at = models.DateTimeField(
        _("Enrichment prompted at"),
        null=True,
        blank=True,
        help_text=_(
            "When the user was shown the one-time profile-enrichment prompt "
            "(set whether they filled it in or skipped, so it is shown once)."
        ),
    )
    enriched_at = models.DateTimeField(
        _("Enriched at"),
        null=True,
        blank=True,
        help_text=_(
            "When the profile was first completed and the rate-limit bonus granted."
        ),
    )

    # Per-user override for the number of application API tokens allowed.
    max_api_tokens = models.PositiveIntegerField(
        _("Max API tokens"),
        null=True,
        blank=True,
        help_text=_(
            "Per-user limit on application API tokens. Leave blank to use the "
            "system default (API_TOKENS_PER_USER_DEFAULT)."
        ),
    )

    created = models.DateTimeField(_("Created"), auto_now_add=True)
    updated = models.DateTimeField(_("Updated"), auto_now=True)

    class Meta:
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")

    def __str__(self):
        return f"Profile of {self.user.username}"

    def get_max_api_tokens(self):
        """Max application API tokens this user may have.

        The per-user ``max_api_tokens`` override wins; otherwise the system
        default ``settings.API_TOKENS_PER_USER_DEFAULT``.
        """
        from django.conf import settings

        if self.max_api_tokens is not None:
            return self.max_api_tokens
        return getattr(settings, "API_TOKENS_PER_USER_DEFAULT", 5)

    @property
    def is_profile_complete(self):
        """True once the user has given the core segmentation data.

        We consider the profile "complete" when both the role and a free-text
        use case are set — that is the data worth incentivising. Organization
        and newsletter opt-in stay optional.
        """
        return bool(self.role) and bool(self.use_case.strip())

    @property
    def is_enrichment_needed(self):
        """Whether to show the one-time on-login enrichment prompt.

        Shown only to users with an incomplete profile who have never been
        prompted before.
        """
        return self.enrichment_prompted_at is None and not self.is_profile_complete

    def mark_enrichment_prompted(self):
        """Record that the enrichment prompt was shown (filled or skipped).

        Idempotent: keeps the first timestamp. Does not save; caller persists.
        """
        if self.enrichment_prompted_at is None:
            self.enrichment_prompted_at = timezone.now()

    def maybe_grant_enrichment_bonus(self):
        """Grant the one-time rate-limit bonus if the profile just completed.

        Returns ``True`` if the bonus was newly granted (so the caller can tell
        the user). Idempotent — only grants once. Does not save; caller
        persists.
        """
        if self.is_profile_complete and self.enriched_at is None:
            self.enriched_at = timezone.now()
            return True
        return False

    @property
    def is_newsletter_subscriber(self):
        """True only when the user opted in AND confirmed via double-opt-in.

        This is the only condition under which marketing mail may be sent.
        """
        return self.newsletter_opt_in and self.newsletter_doi_confirmed_at is not None

    def record_opt_in(self, source):
        """Mark a (pending, unconfirmed) newsletter opt-in request.

        Sets the request timestamp and source but NOT the confirmation — the
        double-opt-in email must still be confirmed before this counts as a
        subscriber. Does not save; caller persists.
        """
        self.newsletter_opt_in = True
        self.newsletter_opt_in_at = timezone.now()
        self.consent_source = source

    def confirm_double_opt_in(self):
        """Mark the double-opt-in as confirmed (link clicked). Does not save."""
        self.newsletter_doi_confirmed_at = timezone.now()

    def revoke_newsletter(self):
        """Unsubscribe: clear opt-in and confirmation. Does not save."""
        self.newsletter_opt_in = False
        self.newsletter_opt_in_at = None
        self.newsletter_doi_confirmed_at = None
