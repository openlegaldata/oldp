import logging

from django.conf import settings
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import LawBook
from oldp.utils.cache_per_user import cache_per_role

logger = logging.getLogger(__name__)


@cache_per_role(settings.CACHE_TTL)
def index_view(request):
    law_books = LawBook.objects.filter(latest=True).order_by("-order")
    cases = list(
        Case.get_queryset(request)
        .defer(*Case.defer_fields_list_view)
        .select_related("court")
        .order_by("-updated_date")
        [:10]
    )

    return render(
        request,
        "homepage/index.html",
        {
            "title": _("Free Access to Legal Data"),
            "nav": "homepage",
            "law_books": law_books,
            "cases": cases,
        },
    )


def error500_view(request, exception=None):
    return render(
        request,
        "errors/500.html",
        {"title": _("Error") + " 500", "exception": exception},
        status=500,
    )


def error404_view(request, exception=None):
    return render(
        request,
        "errors/404.html",
        {"title": "%s - %s" % (_("Error"), _("Not found")), "exception": exception},
        status=404,
    )


def error_permission_denied_view(request, exception=None):
    return render(
        request,
        "errors/permission_denied.html",
        {
            "title": "%s - %s" % (_("Error"), _("Permission denied")),
            "exception": exception,
        },
        status=401,
    )


def error_bad_request_view(request, exception=None):
    return render(
        request,
        "errors/bad_request.html",
        {"title": "%s - %s" % (_("Error"), _("Bad request")), "exception": exception},
        status=400,
    )
