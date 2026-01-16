from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.models import APIToken, APITokenPermission, APITokenPermissionGroup


@admin.register(APITokenPermission)
class APITokenPermissionAdmin(admin.ModelAdmin):
    """Admin interface for individual API token permissions"""

    list_display = ["permission_string", "resource", "action", "description_short", "usage_count"]
    list_filter = ["resource", "action"]
    search_fields = ["resource", "action", "description"]
    ordering = ["resource", "action"]

    fieldsets = (
        (_("Permission Details"), {
            "fields": ("resource", "action", "description")
        }),
    )

    def permission_string(self, obj):
        """Display permission as resource:action"""
        return format_html('<code>{}</code>', obj.get_permission_string())
    permission_string.short_description = _("Permission")
    permission_string.admin_order_field = "resource"

    def description_short(self, obj):
        """Display truncated description"""
        if obj.description:
            return obj.description[:50] + "..." if len(obj.description) > 50 else obj.description
        return "-"
    description_short.short_description = _("Description")

    def usage_count(self, obj):
        """Show how many permission groups use this permission"""
        count = obj.permission_groups.count()
        return format_html(
            '<span title="{}">{}</span>',
            _("Used in {} permission group(s)").format(count),
            count
        )
    usage_count.short_description = _("Usage")


@admin.register(APITokenPermissionGroup)
class APITokenPermissionGroupAdmin(admin.ModelAdmin):
    """Admin interface for API token permission groups"""

    list_display = [
        "name",
        "is_default",
        "permission_count",
        "token_count",
        "created",
        "updated"
    ]
    list_filter = ["is_default", "created"]
    search_fields = ["name", "description"]
    filter_horizontal = ["permissions"]
    ordering = ["name"]

    fieldsets = (
        (_("Group Information"), {
            "fields": ("name", "description", "is_default")
        }),
        (_("Permissions"), {
            "fields": ("permissions",),
            "description": _("Select the permissions that tokens in this group will have access to.")
        }),
        (_("Timestamps"), {
            "fields": ("created", "updated"),
            "classes": ("collapse",)
        }),
    )

    readonly_fields = ["created", "updated"]

    def permission_count(self, obj):
        """Show number of permissions in this group"""
        count = obj.permissions.count()
        permissions = obj.get_permission_list()
        return format_html(
            '<span title="{}">{}</span>',
            ", ".join(permissions) if permissions else _("No permissions"),
            count
        )
    permission_count.short_description = _("Permissions")

    def token_count(self, obj):
        """Show number of tokens using this group"""
        count = obj.tokens.count()
        return format_html(
            '<a href="/admin/accounts/apitoken/?permission_group__id__exact={}">{}</a>',
            obj.id,
            count
        )
    token_count.short_description = _("Tokens")

    def save_model(self, request, obj, form, change):
        """Ensure only one default permission group exists"""
        if obj.is_default:
            # Set all other groups to non-default
            APITokenPermissionGroup.objects.exclude(pk=obj.pk).update(is_default=False)
        super().save_model(request, obj, form, change)


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
        "permission_group_display",
        "is_active",
        "created",
        "last_used",
        "expires_at",
        "is_expired_display"
    ]
    list_filter = ["is_active", "permission_group", "created", "expires_at"]
    search_fields = ["user__username", "user__email", "name", "key"]
    readonly_fields = ["key", "created", "last_used"]
    ordering = ["-created"]

    fieldsets = (
        (_("Token Information"), {
            "fields": ("key", "name", "user")
        }),
        (_("Permissions"), {
            "fields": ("permission_group", "scopes"),
            "description": _("Permission group defines what resources this token can access. "
                           "Legacy scopes field is deprecated.")
        }),
        (_("Status"), {
            "fields": ("is_active",)
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

    def permission_group_display(self, obj):
        """Display the permission group with a link"""
        if obj.permission_group:
            return format_html(
                '<a href="/admin/accounts/apitokenpermissiongroup/{}/change/">{}</a>',
                obj.permission_group.id,
                obj.permission_group.name
            )
        return format_html('<span style="color: orange;">{}</span>', _("No group (legacy)"))
    permission_group_display.short_description = _("Permission Group")
    permission_group_display.admin_order_field = "permission_group__name"

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
        return qs.select_related("user", "permission_group")
