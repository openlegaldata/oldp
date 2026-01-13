from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.models import APIToken


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    """Admin interface for API tokens with enhanced management capabilities"""

    list_display = ["key_masked", "user_link", "created", "token_actions"]
    list_filter = ["created"]
    search_fields = ["user__username", "user__email", "key"]
    readonly_fields = ["key", "created", "user"]
    ordering = ["-created"]

    # Disable add permission since tokens should be created via user registration
    def has_add_permission(self, request):
        return False

    def key_masked(self, obj):
        """Display masked token key for security"""
        if obj.key:
            return format_html(
                '<code>{}...{}</code>',
                obj.key[:4],
                obj.key[-4:]
            )
        return "-"
    key_masked.short_description = _("API Token")
    key_masked.admin_order_field = "key"

    def user_link(self, obj):
        """Display user with link to user admin page"""
        if obj.user:
            return format_html(
                '<a href="/admin/auth/user/{}/change/">{}</a>',
                obj.user.id,
                obj.user.username
            )
        return "-"
    user_link.short_description = _("User")
    user_link.admin_order_field = "user__username"

    def token_actions(self, obj):
        """Display action buttons for token management"""
        return format_html(
            '<a class="button" href="#" onclick="return confirm(\'{}\')">{}</a>',
            _("Are you sure you want to revoke this token?"),
            _("Revoke")
        )
    token_actions.short_description = _("Actions")

    actions = ["revoke_tokens"]

    def revoke_tokens(self, request, queryset):
        """Bulk action to revoke (delete) selected tokens"""
        count = queryset.count()
        queryset.delete()
        self.message_user(
            request,
            _("{} token(s) were successfully revoked.").format(count)
        )
    revoke_tokens.short_description = _("Revoke selected tokens")

    fieldsets = (
        (_("Token Information"), {
            "fields": ("key", "user", "created")
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related to reduce database queries"""
        qs = super().get_queryset(request)
        return qs.select_related("user")


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    """Admin interface for the new multi-token system"""

    list_display = [
        "key_masked",
        "name",
        "user_link",
        "is_active",
        "created",
        "last_used",
        "expires_at",
        "is_expired_display"
    ]
    list_filter = ["is_active", "created", "expires_at"]
    search_fields = ["user__username", "user__email", "name", "key"]
    readonly_fields = ["key", "created", "last_used"]
    ordering = ["-created"]

    fieldsets = (
        (_("Token Information"), {
            "fields": ("key", "name", "user")
        }),
        (_("Status"), {
            "fields": ("is_active", "scopes")
        }),
        (_("Timestamps"), {
            "fields": ("created", "last_used", "expires_at")
        }),
    )

    def key_masked(self, obj):
        """Display masked token key for security"""
        if obj.key:
            return format_html(
                '<code>{}...{}</code>',
                obj.key[:4],
                obj.key[-4:]
            )
        return "-"
    key_masked.short_description = _("API Token")
    key_masked.admin_order_field = "key"

    def user_link(self, obj):
        """Display user with link to user admin page"""
        if obj.user:
            return format_html(
                '<a href="/admin/auth/user/{}/change/">{}</a>',
                obj.user.id,
                obj.user.username
            )
        return "-"
    user_link.short_description = _("User")
    user_link.admin_order_field = "user__username"

    def is_expired_display(self, obj):
        """Display whether token is expired"""
        if obj.is_expired():
            return format_html('<span style="color: red;">✗ {}</span>', _("Expired"))
        elif obj.expires_at:
            return format_html('<span style="color: green;">✓ {}</span>', _("Valid"))
        return format_html('<span style="color: blue;">∞ {}</span>', _("Never"))
    is_expired_display.short_description = _("Expiration Status")

    actions = ["revoke_tokens", "activate_tokens", "deactivate_tokens"]

    def revoke_tokens(self, request, queryset):
        """Bulk action to revoke (delete) selected tokens"""
        count = queryset.count()
        queryset.delete()
        self.message_user(
            request,
            _("{} token(s) were successfully revoked.").format(count)
        )
    revoke_tokens.short_description = _("Revoke selected tokens")

    def activate_tokens(self, request, queryset):
        """Bulk action to activate selected tokens"""
        count = queryset.update(is_active=True)
        self.message_user(
            request,
            _("{} token(s) were successfully activated.").format(count)
        )
    activate_tokens.short_description = _("Activate selected tokens")

    def deactivate_tokens(self, request, queryset):
        """Bulk action to deactivate selected tokens"""
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            _("{} token(s) were successfully deactivated.").format(count)
        )
    deactivate_tokens.short_description = _("Deactivate selected tokens")

    def get_queryset(self, request):
        """Optimize queryset with select_related to reduce database queries"""
        qs = super().get_queryset(request)
        return qs.select_related("user")
