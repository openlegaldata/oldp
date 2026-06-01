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

from oldp.apps.search.api import SearchQueryBuilder
from oldp.apps.search.utils import (
    apply_citation_filter,
    is_search_backend_error,
    is_search_backend_timeout,
    parse_citation_params,
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
    parsed = parse_citation_params(data)
    if parsed is None:
        return None

    kind, token = parsed
    if kind == "law":
        from oldp.apps.laws.models import Law

        book = data.get("cited_law_book", "").strip()
        section = data.get("cited_law_section", "").strip()
        law = (
            Law.objects.filter(book__slug=book, slug=section, book__latest=True)
            .select_related("book")
            .first()
        )
        return {
            "kind": "law",
            "token": token,
            "label": law.get_title() if law else None,
            "params": {"cited_law_book": book, "cited_law_section": section},
        }

    from oldp.apps.cases.models import Case

    case = Case.objects.filter(pk=int(token)).select_related("court").first()
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
        "token": token,
        "label": label,
        "params": {"cited_case": token},
    }


class CustomSearchForm(FacetedSearchForm):
    """Our custom search form for facet search with haystack"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def search(self):
        """Compose keyword, selected facets, date range, and citation filters.

        Inlined instead of calling ``super().search()`` because Haystack's
        ``SearchForm.search`` returns ``EmptySearchQuerySet`` whenever ``q``
        is empty, and chaining ``.narrow()`` / ``.filter()`` onto Empty
        stays Empty — so facets-only or citation-only requests would
        silently return zero results. We start from ``self.searchqueryset``
        (the highlighted, date-faceted SQS the view prepared) and apply
        each filter explicitly. The narrow loop mirrors the few lines of
        ``FacetedSearchForm.search`` so users keep both keyword and
        selected facets across every combination.
        """
        if not self.is_valid():
            return self.no_query_found()

        q = (self.cleaned_data.get("q") or "").strip()
        selected_facets = list(getattr(self, "selected_facets", []) or [])
        start_date = self.data.get("start_date", "")
        end_date = self.data.get("end_date", "")
        order_by = (self.data.get("order_by") or "").strip().lower()
        citation_params = parse_citation_params(self.data)

        if not (q or selected_facets or start_date or end_date or citation_params):
            return self.no_query_found()

        sqs = self.searchqueryset
        if q:
            sqs = sqs.auto_query(q)
        if self.load_all:
            sqs = sqs.load_all()
        for facet in selected_facets:
            if ":" not in facet:
                continue
            field, value = facet.split(":", 1)
            if value:
                sqs = sqs.narrow('%s:"%s"' % (field, sqs.query.clean(value)))

        builder = SearchQueryBuilder(queryset=sqs)
        builder.apply_date_range(start_date, end_date)
        sqs = builder.build()

        # Citation graph filter — clamps to Case because ``cited_laws`` /
        # ``cited_cases`` are not populated on the Law index documents.
        sqs = apply_citation_filter(sqs, self.data)

        # Optional ordering. Default (empty / "relevance") leaves ES's
        # relevance scoring untouched. ``date`` orders newest-first.
        # Anything else is silently ignored to keep URLs forgiving.
        if order_by == "date":
            sqs = sqs.order_by("-date")
        return sqs


class CustomSearchView(FacetedSearchView):
    """Custom search view for haystack.

    Composes keyword (``q``), selected facets, date range, citation-graph
    filters (``cited_law_book`` + ``cited_law_section`` or ``cited_case``),
    and an ``order_by`` toggle into a single SearchQuerySet via
    :class:`CustomSearchForm`. See ``docs/search.md`` for the full filter
    matrix and combined-search semantics.
    """

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

        # Normalize order_by — anything other than "date" collapses to
        # the empty default so the template's truthy check renders
        # "relevance" in the count label and selects the right option in
        # the sort dropdown.
        order_by = (self.request.GET.get("order_by") or "").strip().lower()
        if order_by != "date":
            order_by = ""

        context.update(
            {
                "title": _("Search") + " " + context["query"][:30],
                "search_facets": self.get_search_facets(context),
                "citation_filter": citation_filter,
                "clear_citation_url": clear_citation_url,
                # Round-trip every currently-selected facet through the
                # facets sidebar and year-tile links so submitting the
                # date-range form or clicking a year does not drop them.
                "selected_facets": selected_facets,
                "order_by": order_by,
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
