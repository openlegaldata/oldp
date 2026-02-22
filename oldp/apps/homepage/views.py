import logging

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook
from oldp.utils.cache_per_user import cache_per_role

logger = logging.getLogger(__name__)


def _host_lang_cache_key(request, base_key: str) -> str:
    try:
        host = request.get_host()
    except Exception:
        host = request.META.get("HTTP_HOST", "unknown")
    lang = getattr(request, "LANGUAGE_CODE", None) or "default"
    return f"{base_key}:{host}:{lang}"


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

    laws_count_cache_key = _host_lang_cache_key(request, "homepage_laws_count")
    laws_count = cache.get(laws_count_cache_key)
    if laws_count is None:
        laws_count = "{:,}".format(Law.objects.count())
        cache.set(laws_count_cache_key, laws_count, 60 * 60)

    cases_count_cache_key = _host_lang_cache_key(request, "homepage_cases_count")
    cases_count = cache.get(cases_count_cache_key)
    if cases_count is None:
        cases_count = "{:,}".format(Case.get_queryset(request).count())
        cache.set(cases_count_cache_key, cases_count, 60 * 60)

    return render(
        request,
        "homepage/index.html",
        {
            "title": _("Free Access to Legal Data"),
            "nav": "homepage",
            "law_books": law_books,
            "cases": cases,
            "laws_count": laws_count,
            "cases_count": cases_count,
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
