from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.models import APIToken


@login_required
def profile_view(request):
    return render(request, "accounts/profile.html", {"title": "Profile"})


@login_required
def api_view(request):
    token, created = Token.objects.get_or_create(user=request.user)
    return render(request, "accounts/api.html", {"token": token.key})


@login_required
def api_renew_view(request):
    # Delete existing token and create a new one
    Token.objects.filter(user=request.user).delete()
    token = Token.objects.create(user=request.user)

    messages.success(request, _("Your API access token has been renewed successfully."))

    return redirect(reverse("account_api"))


# Multi-token system views


@login_required
def api_tokens_list_view(request):
    """Display all API tokens for the current user"""
    tokens = APIToken.objects.filter(user=request.user).order_by("-created")
    return render(request, "accounts/api_tokens.html", {
        "tokens": tokens,
        "title": _("API Tokens")
    })


@login_required
def api_token_create_view(request):
    """Create a new API token"""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()

        if not name:
            messages.error(request, _("Token name is required."))
            return redirect(reverse("account_api_tokens"))

        # Optional: Set expiration (default: 1 year)
        expiration_days = int(request.POST.get("expiration_days", 365))
        expires_at = None
        if expiration_days > 0:
            expires_at = timezone.now() + timedelta(days=expiration_days)

        # Create the token
        token = APIToken.objects.create(
            user=request.user,
            name=name,
            expires_at=expires_at
        )

        messages.success(
            request,
            _("API token '{}' has been created successfully. Make sure to copy it now - you won't be able to see it again!").format(name)
        )

        # Redirect to list view with the new token key in session for one-time display
        request.session["new_token_key"] = token.key
        request.session["new_token_id"] = token.id

        return redirect(reverse("account_api_tokens"))

    return render(request, "accounts/api_token_create.html", {
        "title": _("Create API Token")
    })


@login_required
def api_token_revoke_view(request, token_id):
    """Revoke (delete) an API token"""
    token = get_object_or_404(APIToken, id=token_id, user=request.user)

    if request.method == "POST":
        token_name = token.name
        token.delete()

        messages.success(
            request,
            _("API token '{}' has been revoked successfully.").format(token_name)
        )

        return redirect(reverse("account_api_tokens"))

    return render(request, "accounts/api_token_revoke.html", {
        "token": token,
        "title": _("Revoke API Token")
    })
