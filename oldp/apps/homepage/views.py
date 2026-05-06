import logging

from django.conf import settings
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import LawBook
from oldp.utils.cache_per_user import cache_per_role

logger = logging.getLogger(__name__)

# Registers "View all laws" as a translatable msgid so it survives
# makemessages runs. The string is rendered by the oldp-de theme
# template (oldp-de/src/oldp_de/assets/templates/homepage/index.html);
# without this anchor makemessages can't see it (LOCALE_PATHS doesn't
# reach the sibling theme directory) and re-obsoletes the translation.
# Cases get the equivalent treatment via SortableColumn(_("Case")) in
# oldp.apps.cases.views; this is the homepage analogue.
_HOMEPAGE_VIEW_ALL_LAWS_LABEL = _("View all laws")


@cache_per_role(settings.CACHE_TTL)
def index_view(request):
    # Surface the same curated set used by /law/ (settings.TOP_LAW_BOOKS).
    # Empty / unset → no books on the homepage; the section heading stays
    # but the list renders empty.
    top_slugs = [s.strip() for s in settings.TOP_LAW_BOOKS if s and s.strip()]
    if top_slugs:
        by_slug = {
            b.slug: b
            for b in LawBook.get_queryset(request).filter(
                latest=True, slug__in=top_slugs
            )
        }
        law_books = [by_slug[s] for s in top_slugs if s in by_slug]
    else:
        law_books = []
    cases = list(
        Case.get_queryset(request)
        .defer(*Case.defer_fields_list_view)
        .select_related("court")
        .order_by("-updated_date")[:10]
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
