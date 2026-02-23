import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

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
        return (
            Case.get_queryset(self.request)
            .select_related("court")
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
    # Layer 1: Shared case data (one cache entry per case)
    case_cache_key = "case_data_%s" % case_slug
    cached = cache.get(case_cache_key)
    if cached is None:
        qs = Case.get_queryset(request).select_related("court", "source")
        item = get_object_or_404(qs, slug=case_slug)
        ref_markers = list(item.get_reference_markers())
        # Materialize shared, template-driven relations once so warm requests
        # only need user-specific annotation queries.
        item.references = list(item.get_references())
        related_cases = item.get_related()
        cached = (item, ref_markers, related_cases)
        cache.set(case_cache_key, cached, settings.CACHE_TTL)
    else:
        item, ref_markers, related_cases = cached

    # Layer 2: User-specific annotation data (fresh per request)
    user_markers_qs = None
    if request.user.is_authenticated:
        user_markers_qs = item.get_markers(request)
        user_markers = list(user_markers_qs)
        content = insert_markers(item.content or "", ref_markers + user_markers)
    else:
        # Anonymous users only see public markers, so this can be shared.
        public_markers_cache_key = "case_public_markers_%s" % case_slug
        user_markers = cache.get(public_markers_cache_key)
        if user_markers is None:
            user_markers = list(item.get_markers(request))
            cache.set(public_markers_cache_key, user_markers, settings.CACHE_TTL)

        content_cache_key = "case_content_anon_%s" % case_slug
        content = cache.get(content_cache_key)
        if content is None:
            content = insert_markers(item.content or "", ref_markers + user_markers)
            cache.set(content_cache_key, content, settings.CACHE_TTL)

    if request.user.is_staff:
        marker_labels = (
            user_markers_qs
            .values("label__id", "label__name", "label__color", "label__private")
            .annotate(count=Count("label"))
            .order_by("count")
        )
        annotation_labels = item.get_annotation_labels(request)
    else:
        marker_labels = None
        annotation_labels = None

    return render(
        request,
        "cases/case.html",
        {
            "title": item.get_title(),
            "item": item,
            "content": content,
            "related_cases": related_cases,
            "annotation_labels": annotation_labels,
            "marker_labels": marker_labels,
            "line_counter": Counter(),
            "nav": "cases",
        },
    )


def short_url_view(request, pk):
    """Redirects to detail view"""
    item = get_object_or_404(Case.get_queryset(request).only("slug"), pk=pk)

    return redirect(item.get_absolute_url(), permanent=True)
