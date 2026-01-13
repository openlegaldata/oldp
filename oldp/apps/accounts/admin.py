from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token


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
