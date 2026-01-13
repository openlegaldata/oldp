from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token


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
