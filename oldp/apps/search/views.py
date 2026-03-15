import datetime
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from haystack.forms import FacetedSearchForm
from haystack.generic_views import FacetedSearchView
from haystack.query import SearchQuerySet

from oldp.apps.search.utils import is_search_backend_error
from oldp.utils.limited_paginator import LimitedPaginator

logger = logging.getLogger(__name__)


def _normalize_autocomplete_query(query: str) -> str:
    return (query or "").strip()


def _get_autocomplete_cache_key(request, query: str) -> str:
    normalized = _normalize_autocomplete_query(query)
    normalized_key_query = normalized.lower()
    try:
        host = request.get_host()
    except Exception:
        host = request.META.get("HTTP_HOST", "unknown")
    lang = getattr(request, "LANGUAGE_CODE", None) or "default"
    cache_basis = f"{host}|{lang}|{normalized_key_query}"
    digest = hashlib.md5(cache_basis.encode("utf-8")).hexdigest()
    return f"autocomplete_v2_{digest}"


class CustomSearchForm(FacetedSearchForm):
    """Our custom search form for facet search with haystack"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def search(self):
        # First, store the SearchQuerySet received from other processing.
        sqs = super().search()

        if not self.is_valid():
            return self.no_query_found()

        # Custom date range filter
        # TODO can this be done with native-haystack?
        if "start_date" in self.data:
            try:
                sqs = sqs.filter(
                    date__gte=datetime.datetime.strptime(
                        self.data.get("start_date"), "%Y-%m-%d"
                    )
                )
            except ValueError:
                logger.error("Invalid start_date")

        if "end_date" in self.data:
            try:
                sqs = sqs.filter(
                    date__lte=datetime.datetime.strptime(
                        self.data.get("end_date"), "%Y-%m-%d"
                    )
                )
            except ValueError:
                logger.error("Invalid end_date")

        return sqs


class CustomSearchView(FacetedSearchView):
    """Custom search view for haystack."""

    form_class = CustomSearchForm
    paginator_class = LimitedPaginator
    paginate_by = settings.PAGINATE_BY
    facet_fields = [
        "facet_model_name",
        # Law facets
        "book_code",
        # Case facets
        "decision_type",
        "court",
        "court_jurisdiction",
        "court_level_of_appeal",
        "date",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.highlight()
        qs = qs.date_facet(
            "date",
            start_date=datetime.date(2009, 6, 7),
            end_date=datetime.date.today(),
            gap_by="year",
            # gap_amount=1,
        )
        return qs

    def _get_search_facets_cache_key(self):
        try:
            host = self.request.get_host()
        except Exception:
            host = self.request.META.get("HTTP_HOST", "unknown")
        lang = getattr(self.request, "LANGUAGE_CODE", None) or "default"
        cache_basis = f"{host}|{lang}|{self.request.get_full_path()}"
        digest = hashlib.md5(cache_basis.encode("utf-8")).hexdigest()
        return f"search_facets_v1_{digest}"

    def _build_search_facets(self, context):
        """Convert haystack facets to make it easier to build a nice facet sidebar"""
        selected_facets = {}
        qs_facets = self.request.GET.getlist("selected_facets")

        for qp in qs_facets:
            tmp = qp.split("_exact:")

            if len(tmp) == 2:
                selected_facets[tmp[0]] = tmp[1]

            else:
                tmp2 = qp.split(":")

                if len(tmp2) == 2:
                    selected_facets[tmp2[0]] = tmp2[1]

        facets = {}

        if "fields" in context["facets"]:
            for facet_name in context["facets"]["fields"]:
                # if self.request.GET[facet_name]
                facets[facet_name] = {
                    "name": facet_name,
                    "selected": facet_name in selected_facets,
                    "choices": [],
                }

                # All choices
                for facet_choices in context["facets"]["fields"][facet_name]:
                    value, count = facet_choices
                    selected = (
                        facet_name in selected_facets
                        and selected_facets[facet_name] == value
                    )
                    url_param = facet_name + "_exact:%s" % value
                    qs = self.request.GET.copy()

                    if selected:
                        # Remove current facet from url
                        _selected_facets = []
                        for f in qs.getlist("selected_facets"):
                            if f != url_param:
                                _selected_facets.append(f)

                        del qs["selected_facets"]
                        qs.setlist("selected_facets", _selected_facets)

                    else:
                        # Add facet to url
                        qs.update({"selected_facets": url_param})

                    # Filter links should not have pagination
                    if "page" in qs:
                        del qs["page"]

                    if facet_name == "facet_model_name":
                        value = gettext(value)

                    facets[facet_name]["choices"].append(
                        {
                            "facet_name": facet_name,
                            "value": value,
                            "count": count,
                            "selected": selected,
                            "url": "?" + qs.urlencode(),
                        }
                    )

                # Remove empty facets
                if not facets[facet_name]["choices"]:
                    del facets[facet_name]

        return facets

    def get_search_facets(self, context):
        cache_key = self._get_search_facets_cache_key()
        cached_facets = cache.get(cache_key)
        if cached_facets is not None:
            return cached_facets

        facets = self._build_search_facets(context)
        cache.set(cache_key, facets, settings.CACHE_TTL)
        return facets

    def get_context_data(self, *args, **kwargs):
        try:
            context = super().get_context_data(**kwargs)
        except Exception as exc:
            if is_search_backend_error(exc):
                logger.error("Search backend unavailable: %s", exc)
                context = {"query": self.request.GET.get("q", ""), "facets": {}}
                context.update(
                    {
                        "title": _("Search"),
                        "search_error": _(
                            "Search is currently unavailable. Please try again later."
                        ),
                        "search_facets": {},
                    }
                )
                return context
            raise

        search_from = self.request.GET.get("from")
        selected_facets = self.request.GET.getlist("selected_facets")
        logger.debug(
            "Search query: %s (from=%s, facets=%s)",
            context["query"],
            search_from,
            selected_facets or None,
        )

        # TODO data facets are disabled for now
        # date_facets = {}

        # if 'dates' in context['facets'] and 'date' in context['facets']['dates']:  # we assume that dates are already sorted
        #     dates = context['facets']['dates']['date']

        #     if len(dates) > 1:
        #         fmt = '%Y-%m-%d'
        #         date_facets = {
        #             'start_date': dates[0][0].strftime(fmt),
        #             'end_date': dates[-1][0].strftime(fmt),
        #             'items': [{'date': date.strftime(fmt), 'count': count} for date, count in dates],
        #         }

        context.update(
            {
                "title": _("Search") + " " + context["query"][:30],
                "search_facets": self.get_search_facets(context),
                # 'date_facets': date_facets,
            }
        )

        return context


def autocomplete_view(request):
    """Stub for auto-complete feature(title for all objects missing)"""
    suggestions_limit = 5
    query = _normalize_autocomplete_query(request.GET.get("q", ""))

    if not query:
        return JsonResponse({"results": []})

    cache_key = _get_autocomplete_cache_key(request, query)
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"results": cached})

    try:
        sqs = SearchQuerySet().autocomplete(title=query)[:suggestions_limit]
        suggestions = [result.title for result in sqs]
    except Exception as e:
        logger.error("Autocomplete search failed for query '%s': %s", query, str(e))
        if is_search_backend_error(e):
            return JsonResponse(
                {"error": "Search is currently unavailable."},
                status=503,
            )
        return JsonResponse({"results": []})

    cache.set(cache_key, suggestions, settings.CACHE_TTL)
    return JsonResponse({"results": suggestions})
