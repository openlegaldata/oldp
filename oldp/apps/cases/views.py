import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from oldp.apps.cases.cache import (
    CASE_CONTENT_ANON_KEY,
    CASE_DATA_KEY,
    CASE_PUBLIC_MARKERS_KEY,
)
from oldp.apps.cases.filters import CaseFilter
from oldp.apps.cases.models import Case
from oldp.apps.lib.apps import Counter
from oldp.apps.lib.markers import insert_markers
from oldp.apps.lib.views import SortableColumn, SortableFilterView
from oldp.utils.limited_paginator import LimitedPaginator

logger = logging.getLogger(__name__)


class CaseFilterView(SortableFilterView):
    """Index view for cases with filters + sortable"""

    filterset_class = CaseFilter
    paginate_by = settings.PAGINATE_BY
    paginator_class = LimitedPaginator

    columns = [
        SortableColumn(_("Case"), "title", False, ""),
        SortableColumn(
            _("File number"), "file_number", True, "text-nowrap d-none d-md-table-cell"
        ),
        SortableColumn(
            _("Publication date"), "date", True, "text-nowrap d-none d-md-table-cell"
        ),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_queryset(self):
        # Use ``prefetch_related("court")`` rather than
        # ``select_related("court")`` for the same reason the homepage
        # and ``/api/cases/`` list view do: pairing the court JOIN with
        # ``ORDER BY -date LIMIT N`` made MariaDB pick ``courts_court``
        # as the leading table and scan ~1k courts then materialise
        # ~240k rows into a temp table before the filesort, taking
        # 3-6s on prod. Splitting the JOIN out lets the planner
        # index-walk ``cases_case_date_05882e4a`` directly; the
        # prefetch then batches all unique courts for the page into
        # one follow-up query.
        return (
            Case.get_queryset(self.request)
            .prefetch_related("court")
            .defer(*Case.defer_fields_list_view)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Build API-params
        api_params = self.get_filterset_kwargs(self.filterset_class)["data"].copy()  # type: QueryDict

        # Strip page parameter
        if "page" in api_params:
            del api_params["page"]

        context.update(
            {
                "nav": "cases",
                "title": _("Cases"),
                "filter_data": self.get_filterset_kwargs(self.filterset_class)["data"],
                # URL to API endpoint
                "api_url": reverse("api-root") + "cases/?" + api_params.urlencode(),
                "max_display_count": settings.PAGINATE_BY * settings.PAGINATE_UNTIL,
            }
        )
        return context


def case_view(request, case_slug):
    """Case detail view with two-layer caching.

    Layer 1: Shared case data (Case object + reference markers) cached per case slug.
    Layer 2: User-specific annotation data fetched fresh per request.
    """
    # Layer 1: Shared case data (one cache entry per case).
    # The cache key is slug-only, so anything we store here is served to
    # every requester regardless of role. Only accepted cases are publicly
    # visible, so we cache only those — otherwise a staff/creator preview
    # would poison the cache and expose pending/rejected cases to anon.
    case_cache_key = CASE_DATA_KEY % case_slug
    cached = cache.get(case_cache_key)
    if cached is None:
        qs = Case.get_queryset(request).select_related("court", "source")
        item = get_object_or_404(qs, slug=case_slug)
        ref_markers = list(item.get_reference_markers())
        # Materialize shared, template-driven relations once so warm requests
        # only need user-specific annotation queries.
        item.references = list(item.get_references())
        cached = (item, ref_markers)
        if item.review_status == "accepted":
            cache.set(case_cache_key, cached, settings.CACHE_TTL)
    else:
        item, ref_markers = cached

    # Layer 2: User-specific annotation data (fresh per request)
    user_markers_qs = None
    if request.user.is_authenticated:
        user_markers_qs = item.get_markers(request)
        user_markers = list(user_markers_qs)
        content = insert_markers(item.content or "", ref_markers + user_markers)
    else:
        # Anonymous users only see public markers, so this can be shared.
        # Skip writes for non-accepted cases for the same reason Layer 1 does.
        can_cache_anon = item.review_status == "accepted"
        public_markers_cache_key = CASE_PUBLIC_MARKERS_KEY % case_slug
        user_markers = cache.get(public_markers_cache_key)
        if user_markers is None:
            user_markers = list(item.get_markers(request))
            if can_cache_anon:
                cache.set(public_markers_cache_key, user_markers, settings.CACHE_TTL)

        content_cache_key = CASE_CONTENT_ANON_KEY % case_slug
        content = cache.get(content_cache_key)
        if content is None:
            content = insert_markers(item.content or "", ref_markers + user_markers)
            if can_cache_anon:
                cache.set(content_cache_key, content, settings.CACHE_TTL)

    if request.user.is_staff:
        marker_labels = (
            user_markers_qs.values(
                "label__id", "label__name", "label__color", "label__private"
            )
            .annotate(count=Count("label"))
            .order_by("count")
        )
        annotation_labels = item.get_annotation_labels(request)
    else:
        marker_labels = None
        annotation_labels = None

    # Citing-cases panel — symmetric to the law detail view. Backed by
    # the ``cited_cases`` field on ``CaseIndex`` (multi-value list of
    # the case PKs each case cites). The ES inverted index makes this
    # ~50ms cold; falling back to a SQL JOIN at this scale would be
    # the same disease the law detail view used to suffer. On ES
    # failure the template surfaces a "search unavailable" notice plus
    # a link to the filtered search page.
    from oldp.apps.search.utils import citing_cases_via_es

    referencing_cases, referencing_cases_count, referencing_cases_error = (
        citing_cases_via_es("cited_cases", str(item.pk))
    )
    referencing_cases_search_url = (
        reverse("haystack_search") + "?" + urlencode({"cited_case": str(item.pk)})
    )

    return render(
        request,
        "cases/case.html",
        {
            "title": item.get_title(),
            "item": item,
            "content": content,
            "annotation_labels": annotation_labels,
            "marker_labels": marker_labels,
            "line_counter": Counter(),
            "nav": "cases",
            "referencing_cases": referencing_cases,
            "referencing_cases_count": referencing_cases_count,
            "referencing_cases_error": referencing_cases_error,
            "referencing_cases_search_url": referencing_cases_search_url,
        },
    )


def short_url_view(request, pk):
    """Redirects to detail view"""
    item = get_object_or_404(Case.get_queryset(request).only("slug"), pk=pk)

    return redirect(item.get_absolute_url(), permanent=True)
