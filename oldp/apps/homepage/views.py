from django.conf import settings
from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.cache import cache_page

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import LawBook


@cache_page(settings.CACHE_TTL)
def index_view(request):
    k = 10
    books = LawBook.objects.filter(latest=True).order_by('-revision_date')[:k]
    cases = Case.get_queryset(request).select_related('court').order_by('-updated_date')[:k]

    return render(request, 'homepage/index.html', {
        'title': _('Free Access to Legal Data'),
        'nav': 'homepage',
        'books': books,
        'cases': cases
    })


def error500_view(request, exception=None):
    return render(request, 'errors/500.html', {
        'title': _('Error') + ' 500',
        'exception': exception
    })


def error404_view(request, exception=None):
    return render(request, 'errors/404.html', {
        'title': _('Error') + ' 404',
        'exception': exception
    })


def error_permission_denied_view(request, exception=None):
    return render(request, 'errors/permission_denied.html', {
        'title': _('Error') + ' - ' + _('Permission denied'),
        'exception': exception
    })


def error_bad_request_view(request, exception=None):
    return render(request, 'errors/bad_request.html', {
        'title': _('Error') + ' - ' + _('Bad request'),
        'exception': exception
    })


def landing_page_view(request):
    return render(request, 'homepage/landing_page.html', {
        'title': _('Free Access to Legal Data')
    })
