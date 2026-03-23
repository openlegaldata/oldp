"""API views for case statistics sub-endpoints.

Each sub-endpoint returns the total count and results grouped by a dimension,
where each result item includes its own total and date-bucketed time series.
"""

import datetime
import logging
from collections import defaultdict

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncMonth, TruncYear
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.response import Response

from oldp.api.mixins import ReviewStatusFilterMixin
from oldp.apps.accounts.permissions import HasTokenPermission
from oldp.apps.cases.models import Case

logger = logging.getLogger(__name__)

VALID_BUCKETS = ("year", "month", "day")
VALID_REVIEW_STATUSES = ("pending", "accepted", "rejected")

TRUNC_FUNCTIONS = {
    "year": TruncYear,
    "month": TruncMonth,
    "day": TruncDay,
}

DATE_FORMATS = {
    "year": "%Y",
    "month": "%Y-%m",
    "day": "%Y-%m-%d",
}

BASE_PARAMETERS = [
    openapi.Parameter(
        "date_after",
        openapi.IN_QUERY,
        type=openapi.TYPE_STRING,
        format="date",
        description="Filter cases with date >= this value (YYYY-MM-DD). Default: one year ago.",
    ),
    openapi.Parameter(
        "date_before",
        openapi.IN_QUERY,
        type=openapi.TYPE_STRING,
        format="date",
        description="Filter cases with date <= this value (YYYY-MM-DD). Default: today.",
    ),
    openapi.Parameter(
        "bucket",
        openapi.IN_QUERY,
        type=openapi.TYPE_STRING,
        enum=list(VALID_BUCKETS),
        description="Time bucket for date grouping. Default: month.",
    ),
    openapi.Parameter(
        "review_status",
        openapi.IN_QUERY,
        type=openapi.TYPE_STRING,
        enum=list(VALID_REVIEW_STATUSES),
        description="Filter by review status (staff only).",
    ),
]

STATS_PARAMETERS = BASE_PARAMETERS + [
    openapi.Parameter(
        "court",
        openapi.IN_QUERY,
        type=openapi.TYPE_INTEGER,
        description="Filter by court ID.",
    ),
    openapi.Parameter(
        "court__state",
        openapi.IN_QUERY,
        type=openapi.TYPE_INTEGER,
        description="Filter by state ID (via court relation).",
    ),
    openapi.Parameter(
        "source",
        openapi.IN_QUERY,
        type=openapi.TYPE_INTEGER,
        description="Filter by source ID.",
    ),
]

BY_COURT_PARAMETERS = BASE_PARAMETERS + [
    openapi.Parameter(
        "court__state",
        openapi.IN_QUERY,
        type=openapi.TYPE_INTEGER,
        required=True,
        description="Filter by state ID (required).",
    ),
    openapi.Parameter(
        "source",
        openapi.IN_QUERY,
        type=openapi.TYPE_INTEGER,
        description="Filter by source ID.",
    ),
]


class CaseStatsViewSet(
    ReviewStatusFilterMixin, viewsets.GenericViewSet, ListModelMixin
):
    """Case statistics grouped by various dimensions.

    Endpoints:
    - /api/cases/stats/ — total count and date-bucketed time series
    - /api/cases/stats/by_country/
    - /api/cases/stats/by_state/
    - /api/cases/stats/by_court/ (requires court__state filter)
    - /api/cases/stats/by_source/

    The root endpoint only supports date range and review_status filters.
    Sub-endpoints additionally support court, state, and source filters.

    Each result item includes its own total and date-bucketed time series.

    Defaults to the last year with monthly buckets.
    Staff users can additionally filter by review_status.
    Non-staff users only see statistics for accepted cases.
    """

    permission_classes = [HasTokenPermission]
    token_resource = "cases"
    http_method_names = ["get", "head", "options"]
    queryset = Case.objects.all()

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def _parse_date(self, value, param_name):
        """Parse an ISO date string, returning None if not provided."""
        if not value:
            return None
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return ValueError(
                f"Invalid date format for '{param_name}': '{value}'. Use YYYY-MM-DD."
            )

    def _build_base_queryset(self, request):
        """Build queryset with date range and review_status filters only.

        Returns (queryset, filters_dict, error_response) where error_response
        is a Response if validation failed, or None on success.
        """
        params = request.query_params

        # Parse and validate bucket
        bucket = params.get("bucket", "month")
        if bucket not in VALID_BUCKETS:
            return (
                None,
                None,
                Response(
                    {
                        "detail": f"Invalid bucket '{bucket}'. Must be one of: {', '.join(VALID_BUCKETS)}."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )

        # Parse dates with defaults: last year
        today = datetime.date.today()
        one_year_ago = today - relativedelta(years=1)

        date_after = self._parse_date(params.get("date_after"), "date_after")
        if isinstance(date_after, ValueError):
            return (
                None,
                None,
                Response(
                    {"detail": str(date_after)}, status=status.HTTP_400_BAD_REQUEST
                ),
            )
        if date_after is None:
            date_after = one_year_ago

        date_before = self._parse_date(params.get("date_before"), "date_before")
        if isinstance(date_before, ValueError):
            return (
                None,
                None,
                Response(
                    {"detail": str(date_before)}, status=status.HTTP_400_BAD_REQUEST
                ),
            )
        if date_before is None:
            date_before = today

        # Build queryset (ReviewStatusFilterMixin handles visibility)
        qs = self.get_queryset()

        # Apply date filters
        qs = qs.filter(date__gte=date_after, date__lte=date_before)

        # Staff-only review_status filter
        review_status = params.get("review_status")
        if review_status and request.user.is_authenticated and request.user.is_staff:
            qs = qs.filter(review_status=review_status)

        filters_dict = {
            "date_after": str(date_after),
            "date_before": str(date_before),
            "bucket": bucket,
        }

        return qs, filters_dict, None

    def _build_filtered_queryset(self, request):
        """Build queryset with all filters (date, review_status, court, state, source).

        Extends _build_base_queryset with dimension-specific filters for sub-endpoints.
        """
        qs, filters_dict, error = self._build_base_queryset(request)
        if error:
            return None, None, error

        params = request.query_params

        court_id = params.get("court")
        if court_id:
            qs = qs.filter(court_id=court_id)

        state_id = params.get("court__state")
        if state_id:
            qs = qs.filter(court__state_id=state_id)

        source_id = params.get("source")
        if source_id:
            qs = qs.filter(source_id=source_id)

        return qs, filters_dict, None

    def _build_buckets(self, qs, bucket):
        """Build time-series buckets from queryset."""
        trunc_fn = TRUNC_FUNCTIONS[bucket]
        date_format = DATE_FORMATS[bucket]
        by_date_qs = (
            qs.filter(date__isnull=False)
            .annotate(period=trunc_fn("date"))
            .values("period")
            .annotate(count=Count("id"))
            .order_by("period")
        )
        return [
            {"date": item["period"].strftime(date_format), "count": item["count"]}
            for item in by_date_qs
        ]

    def _build_grouped_results(self, qs, bucket, group_fields, item_builder):
        """Build results where each item has its own total and date buckets.

        Args:
            qs: Filtered queryset.
            bucket: Time bucket name (year/month/day).
            group_fields: List of field paths to group by (e.g. ["court__id", "court__name"]).
            item_builder: Callable(row_dict) -> dict with item metadata (id, name, etc.).
                          Called once per unique group to build the base item dict.
        """
        trunc_fn = TRUNC_FUNCTIONS[bucket]
        date_format = DATE_FORMATS[bucket]
        id_field = group_fields[0]

        # Single query: group by dimension fields + date bucket
        rows = (
            qs.filter(date__isnull=False)
            .annotate(period=trunc_fn("date"))
            .values(*group_fields, "period")
            .annotate(count=Count("id"))
            .order_by(id_field, "period")
        )

        # Collect per-item buckets and totals
        items = {}
        totals = defaultdict(int)
        for row in rows:
            item_id = row[id_field]
            if item_id not in items:
                items[item_id] = {
                    "meta": item_builder(row),
                    "buckets": [],
                }
            items[item_id]["buckets"].append(
                {"date": row["period"].strftime(date_format), "count": row["count"]}
            )
            totals[item_id] += row["count"]

        # Build final results sorted by total descending
        results = []
        for item_id in sorted(totals, key=totals.get, reverse=True):
            entry = items[item_id]["meta"]
            entry["total"] = totals[item_id]
            entry["buckets"] = items[item_id]["buckets"]
            results.append(entry)

        return results

    def _build_response(self, request, group_fields, item_builder):
        """Build a stats response with total and per-item bucketed results."""
        qs, filters_dict, error = self._build_filtered_queryset(request)
        if error:
            return error

        total = qs.count()
        results = self._build_grouped_results(
            qs, filters_dict["bucket"], group_fields, item_builder
        )

        return Response(
            {
                "filters": filters_dict,
                "total": total,
                "results": results,
            }
        )

    @swagger_auto_schema(
        operation_description=(
            "Overall case statistics: total count and date-bucketed time series. "
            "Only date range and review_status filters are supported."
        ),
        manual_parameters=BASE_PARAMETERS,
    )
    def list(self, request, *args, **kwargs):
        """Return overall case statistics with total and date buckets."""
        qs, filters_dict, error = self._build_base_queryset(request)
        if error:
            return error

        total = qs.count()
        buckets = self._build_buckets(qs, filters_dict["bucket"])

        return Response(
            {
                "filters": filters_dict,
                "total": total,
                "buckets": buckets,
            }
        )

    @swagger_auto_schema(
        operation_description=(
            "Case counts grouped by country. Each country includes "
            "its own total and date-bucketed time series."
        ),
        manual_parameters=STATS_PARAMETERS,
    )
    @action(detail=False, url_path="by_country", url_name="by-country")
    def by_country(self, request):
        """Return case statistics grouped by country."""
        return self._build_response(
            request,
            group_fields=[
                "court__state__country__id",
                "court__state__country__code",
                "court__state__country__name",
            ],
            item_builder=lambda r: {
                "id": r["court__state__country__id"],
                "code": r["court__state__country__code"],
                "name": r["court__state__country__name"],
            },
        )

    @swagger_auto_schema(
        operation_description=(
            "Case counts grouped by state. Each state includes "
            "its own total and date-bucketed time series."
        ),
        manual_parameters=STATS_PARAMETERS,
    )
    @action(detail=False, url_path="by_state", url_name="by-state")
    def by_state(self, request):
        """Return case statistics grouped by state."""
        return self._build_response(
            request,
            group_fields=["court__state__id", "court__state__name"],
            item_builder=lambda r: {
                "id": r["court__state__id"],
                "name": r["court__state__name"],
            },
        )

    @swagger_auto_schema(
        operation_description=(
            "Case counts grouped by court. Each court includes "
            "its own total and date-bucketed time series. "
            "Requires the court__state filter."
        ),
        manual_parameters=BY_COURT_PARAMETERS,
    )
    @action(detail=False, url_path="by_court", url_name="by-court")
    def by_court(self, request):
        """Return case statistics grouped by court. Requires court__state filter."""
        if not request.query_params.get("court__state"):
            return Response(
                {"detail": "The 'court__state' filter is required for this endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return self._build_response(
            request,
            group_fields=["court__id", "court__name"],
            item_builder=lambda r: {
                "id": r["court__id"],
                "name": r["court__name"],
            },
        )

    @swagger_auto_schema(
        operation_description=(
            "Case counts grouped by source. Each source includes "
            "its own total and date-bucketed time series."
        ),
        manual_parameters=STATS_PARAMETERS,
    )
    @action(detail=False, url_path="by_source", url_name="by-source")
    def by_source(self, request):
        """Return case statistics grouped by source."""
        return self._build_response(
            request,
            group_fields=["source__id", "source__name"],
            item_builder=lambda r: {
                "id": r["source__id"],
                "name": r["source__name"],
            },
        )
