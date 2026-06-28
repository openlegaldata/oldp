import time
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.forms import ProfileEnrichmentForm, ProfileForm
from oldp.apps.accounts.models import APIToken, APITokenPermissionGroup
from oldp.apps.accounts.newsletter import read_doi_token, start_double_opt_in

User = get_user_model()


def _enriched_bonus_message():
    """Success message announcing the rate-limit bonus, with the new number."""
    from rest_framework.settings import api_settings

    rate = (api_settings.DEFAULT_THROTTLE_RATES or {}).get("enriched", "")
    requests = rate.split("/")[0] if rate else ""
    if requests:
        return _(
            "Thanks! Your profile is complete and your API rate limit has been "
            "raised to {} requests/hour."
        ).format(requests)
    return _(
        "Thanks! Your profile is complete and your API rate limit has been raised."
    )


@login_required
def profile_view(request):
    """User dashboard: account info, profile, API usage, newsletter status."""
    profile = request.user.profile
    tokens = APIToken.objects.filter(user=request.user)
    active_tokens = tokens.filter(is_active=True)
    last_used = active_tokens.exclude(last_used=None).order_by("-last_used").first()
    # Highest custom rate limit across the user's tokens (None => default rate).
    custom_rate_limit = (
        active_tokens.exclude(rate_limit=None)
        .order_by("-rate_limit")
        .values_list("rate_limit", flat=True)
        .first()
    )
    # Enriched bonus tier (shown when the user completed their profile and has
    # no higher explicit token override).
    from rest_framework.settings import api_settings

    rates = api_settings.DEFAULT_THROTTLE_RATES or {}
    enriched_rate_limit = None
    if profile.enriched_at is not None and rates.get("enriched"):
        enriched_rate_limit = int(rates["enriched"].split("/")[0])

    # Effective hourly limit and live consumption for the current window.
    # The throttle stores per-user request timestamps in the default cache
    # (keyed ``throttle_user_<pk>``); we read the same bucket to show usage.
    # This is best-effort: the cache is ephemeral and only counts API traffic.
    default_user_limit = int(rates["user"].split("/")[0]) if rates.get("user") else 0
    effective_limit = custom_rate_limit or enriched_rate_limit or default_user_limit
    usage_window_seconds = 3600
    now = time.time()
    history = cache.get(f"throttle_user_{request.user.pk}", [])
    usage_used = sum(1 for ts in history if ts > now - usage_window_seconds)
    usage_remaining = max(0, effective_limit - usage_used)
    usage_percent = (
        min(100, round(usage_used / effective_limit * 100)) if effective_limit else 0
    )

    return render(
        request,
        "accounts/profile.html",
        {
            "title": _("Dashboard"),
            "profile": profile,
            "form": ProfileForm(instance=profile),
            "token_count": tokens.count(),
            "active_token_count": active_tokens.count(),
            "last_token_used": last_used.last_used if last_used else None,
            "custom_rate_limit": custom_rate_limit,
            "enriched_rate_limit": enriched_rate_limit,
            "effective_limit": effective_limit,
            "usage_used": usage_used,
            "usage_remaining": usage_remaining,
            "usage_percent": usage_percent,
        },
    )


@login_required
def profile_edit_view(request):
    """Persist edits to the profile segmentation fields from the dashboard."""
    profile = request.user.profile
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            messages.success(request, _("Your profile has been updated."))
            if profile.maybe_grant_enrichment_bonus():
                profile.save(update_fields=["enriched_at", "updated"])
                messages.success(request, _enriched_bonus_message())
            return redirect(reverse("account_profile"))
        # Re-render the dashboard with the bound (invalid) form.
        messages.error(request, _("Please correct the errors below."))
        tokens = APIToken.objects.filter(user=request.user)
        return render(
            request,
            "accounts/profile.html",
            {
                "title": _("Dashboard"),
                "profile": profile,
                "form": form,
                "token_count": tokens.count(),
                "active_token_count": tokens.filter(is_active=True).count(),
                "last_token_used": None,
                "custom_rate_limit": None,
            },
        )
    return redirect(reverse("account_profile"))


@login_required
def newsletter_preference_view(request):
    """Subscribe (start double-opt-in) or unsubscribe from the newsletter."""
    if request.method != "POST":
        return redirect(reverse("account_profile"))

    profile = request.user.profile
    action = request.POST.get("action")

    if action == "subscribe":
        if profile.is_newsletter_subscriber:
            messages.info(request, _("You are already subscribed."))
        else:
            profile.record_opt_in(profile.CONSENT_SOURCE_DASHBOARD)
            profile.save()
            start_double_opt_in(request, profile)
            messages.success(
                request,
                _("Almost done — check your inbox to confirm your subscription."),
            )
    elif action == "unsubscribe":
        profile.revoke_newsletter()
        profile.save()
        messages.success(request, _("You have been unsubscribed."))

    return redirect(reverse("account_profile"))


@login_required
def profile_enrichment_view(request):
    """One-time on-login prompt to complete the profile + newsletter opt-in.

    Shown to existing users with an incomplete profile (see the account
    adapter's login redirect). Both submitting and skipping mark the prompt as
    seen so it never shows again. Completing the profile grants the rate-limit
    bonus; ticking the opt-in starts the double-opt-in flow.
    """
    profile = request.user.profile

    if request.method == "POST":
        # "Skip" just records that we asked, then sends them on their way.
        if "skip" in request.POST:
            profile.mark_enrichment_prompted()
            profile.save()
            return redirect(reverse("account_profile"))

        form = ProfileEnrichmentForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.mark_enrichment_prompted()
            granted = profile.maybe_grant_enrichment_bonus()
            opted_in = form.cleaned_data.get("newsletter_opt_in")
            if opted_in and not profile.newsletter_opt_in:
                profile.record_opt_in(profile.CONSENT_SOURCE_PROMPT)
            profile.save()

            if (
                opted_in
                and profile.newsletter_opt_in
                and not profile.is_newsletter_subscriber
            ):
                start_double_opt_in(request, profile)

            if granted:
                messages.success(request, _enriched_bonus_message())
            else:
                messages.success(request, _("Thanks for updating your profile!"))
            return redirect(reverse("account_profile"))
    else:
        form = ProfileEnrichmentForm(instance=profile)

    return render(
        request,
        "accounts/profile_enrichment.html",
        {"title": _("Complete your profile"), "form": form},
    )


@login_required
def api_view(request):
    token, created = Token.objects.get_or_create(user=request.user)
    return render(request, "accounts/personal_api_tokens.html", {"token": token.key})


@login_required
def api_renew_view(request):
    # Delete existing token and create a new one
    Token.objects.filter(user=request.user).delete()
    Token.objects.create(user=request.user)

    messages.success(request, _("Your API access token has been renewed successfully."))

    return redirect(reverse("account_api"))


# Multi-token system views


@login_required
def api_tokens_list_view(request):
    """Display all API tokens for the current user"""
    tokens = APIToken.objects.filter(user=request.user).order_by("-created")

    # Pop one-time display data for newly created token
    new_token_key = request.session.pop("new_token_key", None)
    new_token_id = request.session.pop("new_token_id", None)

    max_tokens = request.user.profile.get_max_api_tokens()
    token_count = tokens.count()

    return render(
        request,
        "accounts/app_api_tokens.html",
        {
            "tokens": tokens,
            "title": _("API Tokens"),
            "new_token_key": new_token_key,
            "new_token_id": new_token_id,
            "max_tokens": max_tokens,
            "token_count": token_count,
            "at_token_limit": token_count >= max_tokens,
        },
    )


@login_required
def api_token_create_view(request):
    """Create a new API token"""
    # Enforce the per-user token cap (hygiene; rate limiting itself is per-user).
    max_tokens = request.user.profile.get_max_api_tokens()
    if APIToken.objects.filter(user=request.user).count() >= max_tokens:
        messages.error(
            request,
            _(
                "You have reached the maximum number of API tokens ({}). "
                "Revoke an existing token to create a new one."
            ).format(max_tokens),
        )
        return redirect(reverse("account_api_tokens"))

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

        # Create the token, attaching the system-wide default permission
        # group so the token has an explicit (non-NULL) permission_group from
        # the start. ``has_permission`` falls back to is_default when a token
        # has none, but recording the group on the row makes admin/audit
        # views show the actual permissions and avoids surprises if the
        # default flag is later moved to a different group.
        default_group = APITokenPermissionGroup.objects.filter(is_default=True).first()
        token = APIToken.objects.create(
            user=request.user,
            name=name,
            expires_at=expires_at,
            permission_group=default_group,
        )

        messages.success(
            request,
            _(
                "API token '{}' has been created successfully. Make sure to copy it now - you won't be able to see it again!"
            ).format(name),
        )

        # Redirect to list view with the new token key in session for one-time display
        request.session["new_token_key"] = token.key
        request.session["new_token_id"] = token.id

        return redirect(reverse("account_api_tokens"))

    return render(
        request, "accounts/app_api_token_create.html", {"title": _("Create API Token")}
    )


@login_required
def api_token_revoke_view(request, token_id):
    """Revoke (delete) an API token"""
    token = get_object_or_404(APIToken, id=token_id, user=request.user)

    if request.method == "POST":
        token_name = token.name
        token.delete()

        messages.success(
            request,
            _("API token '{}' has been revoked successfully.").format(token_name),
        )

        return redirect(reverse("account_api_tokens"))

    return render(
        request,
        "accounts/app_api_token_revoke.html",
        {"token": token, "title": _("Revoke API Token")},
    )


# Newsletter double-opt-in


def newsletter_confirm_view(request, token):
    """Confirm a newsletter double-opt-in from the emailed link.

    Validates the signed token, marks the profile's double-opt-in as confirmed,
    and renders a result page. Works whether or not the user is logged in (the
    token carries the identity).
    """
    user_pk = read_doi_token(token)
    confirmed = False

    if user_pk is not None:
        user = User.objects.filter(pk=user_pk).select_related("profile").first()
        if user is not None and hasattr(user, "profile"):
            profile = user.profile
            if profile.newsletter_opt_in:
                # Only confirm an actual pending opt-in; ignore stale links for
                # users who already unsubscribed.
                if not profile.newsletter_doi_confirmed_at:
                    profile.confirm_double_opt_in()
                    profile.save(
                        update_fields=["newsletter_doi_confirmed_at", "updated"]
                    )
                confirmed = True

    return render(
        request,
        "accounts/newsletter_confirm.html",
        {"title": _("Newsletter confirmation"), "confirmed": confirmed},
    )
