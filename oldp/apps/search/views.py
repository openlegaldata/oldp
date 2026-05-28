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

from oldp.apps.cases.search_indexes import cited_law_token
from oldp.apps.search.api import SearchQueryBuilder
from oldp.apps.search.utils import (
    is_search_backend_error,
    is_search_backend_timeout,
)
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


def _resolve_citation_filter(data):
    """Resolve ``cited_law_book`` + ``cited_law_section`` / ``cited_case``
    query parameters to the ES filter token + a human-readable label.

    Returns a ``dict`` with keys:

      * ``kind`` — one of ``"law"``, ``"case"``, or ``None``;
      * ``token`` — the value stored in the corresponding ES field
        (``cited_laws`` or ``cited_cases``);
      * ``label`` — display text (e.g. ``"§ 823 BGB"`` or
        ``"VI ZR 123/22 (BGH)"``);
      * ``params`` — the dict of GET params that select this filter,
        used to round-trip the chosen filter through pagination
        URLs without losing it.

    Returns ``None`` when no citation filter is requested. Returns the
    dict with ``label=None`` when the resolved law / case does not
    exist (we still apply the ES filter; the search will just return
    zero hits, which is correct behaviour).
    """
    book = (data.get("cited_law_book") or "").strip()
    section = (data.get("cited_law_section") or "").strip()
    case_id_raw = (data.get("cited_case") or "").strip()

    if book and section:
        from oldp.apps.laws.models import Law

        law = (
            Law.objects.filter(book__slug=book, slug=section, book__latest=True)
            .select_related("book")
            .first()
        )
        label = law.get_title() if law else None
        return {
            "kind": "law",
            "token": cited_law_token(book, section),
            "label": label,
            "params": {"cited_law_book": book, "cited_law_section": section},
        }

    if case_id_raw:
        try:
            case_id = int(case_id_raw)
        except ValueError:
            return None
        from oldp.apps.cases.models import Case

        case = Case.objects.filter(pk=case_id).select_related("court").first()
        if case is not None:
            label = (
                f"{case.file_number} ({case.court.name})"
                if case.court_id
                else case.file_number
            )
        else:
            label = None
        return {
            "kind": "case",
            "token": str(case_id),
            "label": label,
            "params": {"cited_case": str(case_id)},
        }

    return None


class CustomSearchForm(FacetedSearchForm):
    """Our custom search form for facet search with haystack"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def search(self):
        # First, store the SearchQuerySet received from other processing.
        sqs = super().search()

        if not self.is_valid():
            return self.no_query_found()

        # Date range filtering via shared builder
        builder = SearchQueryBuilder(queryset=sqs)
        builder.apply_date_range(
            self.data.get("start_date", ""),
            self.data.get("end_date", ""),
        )
        # Citation graph filters. Both ``cited_laws`` and ``cited_cases``
        # are multi-value fields on ``CaseIndex``; haystack emits a
        # narrow-query like ``cited_laws:"bgb__823"`` which ES resolves
        # against the inverted index in sub-100ms. We also clamp the
        # model to Case here because the citation fields are not
        # populated on ``LawIndex`` documents.
        citation_filter = _resolve_citation_filter(self.data)
        if citation_filter is not None:
            sqs = builder.build()
            if citation_filter["kind"] == "law":
                sqs = sqs.filter(cited_laws=citation_filter["token"])
            else:
                sqs = sqs.filter(cited_cases=citation_filter["token"])
            sqs = sqs.filter(facet_model_name="Case")
            return sqs
        return builder.build()


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
        # Exclude page param — facets are identical across pages of the same query
        params = self.request.GET.copy()
        params.pop("page", None)
        cache_basis = f"{host}|{lang}|{params.urlencode()}"
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
                is_timeout = is_search_backend_timeout(exc)
                # Log timeouts at WARNING so retryable transients don't
                # flood the ERROR channel; reserve ERROR for true outages.
                logger.log(
                    logging.WARNING if is_timeout else logging.ERROR,
                    "Search backend %s (q=%r): %s",
                    "timeout" if is_timeout else "unavailable",
                    self.request.GET.get("q", ""),
                    exc,
                )
                if is_timeout:
                    error_message = _(
                        "Search timed out. The first request after a "
                        "cold start can be slow — please try again."
                    )
                else:
                    error_message = _(
                        "Search is currently unavailable. Please try again later."
                    )
                context = {"query": self.request.GET.get("q", ""), "facets": {}}
                context.update(
                    {
                        "title": _("Search"),
                        "search_error": error_message,
                        "search_retryable": is_timeout,
                        "search_facets": {},
                    }
                )
                return context
            raise

        # Haystack's SearchMixin.form_invalid does not inject "query" into the
        # context (only form_valid does). Fall back to the raw GET param so
        # downstream logging/title code and the template work in both paths.
        context.setdefault("query", self.request.GET.get("q", ""))

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

        citation_filter = _resolve_citation_filter(self.request.GET)
        clear_citation_url = None
        if citation_filter is not None:
            # Build a "remove this filter" URL by stripping the citation
            # params from the current querystring. Keeps q=, facets, etc.
            remaining = self.request.GET.copy()
            for key in ("cited_law_book", "cited_law_section", "cited_case"):
                remaining.pop(key, None)
            remaining.pop("page", None)
            qs = remaining.urlencode()
            clear_citation_url = "?" + qs if qs else "?"

        context.update(
            {
                "title": _("Search") + " " + context["query"][:30],
                "search_facets": self.get_search_facets(context),
                "citation_filter": citation_filter,
                "clear_citation_url": clear_citation_url,
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
