from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from rest_framework.authtoken.models import Token


@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html', {
            'title': 'Profile'
        })


@login_required
def api_view(request):
    token, created = Token.objects.get_or_create(user=request.user)
    return render(request, 'accounts/api.html', {
        'token': token.key
        })


@login_required
def api_renew_view(request):
    token, created = Token.objects.get_or_create(user=request.user)
    token.key = token.generate_key()
    # token.saved()
    # TODO Saving does not work

    messages.warning(request, _('You have a freshly created API access token.'))

    return redirect(reverse('account_api'))
