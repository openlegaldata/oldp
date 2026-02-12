"""Shared base class for creation dashboard admin views."""

import logging
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from oldp.apps.processing.content_processor import ContentProcessor
from oldp.apps.processing.errors import ProcessingError

logger = logging.getLogger(__name__)


@method_decorator(staff_member_required, name="dispatch")
class CreationDashboardView(View):
    """Generic dashboard showing creation statistics with filtering and batch processing.

    Subclasses configure via class attributes:
        model: The Django model class (e.g., Case, Law).
        admin_changelist_url_name: URL name for the admin changelist (e.g., "admin:cases_case_changelist").
        app_label: The app label used in breadcrumbs (e.g., "cases").
        entity_name: Singular display name (e.g., "Case").
        entity_name_plural: Plural display name (e.g., "Cases").
    """

    model = None
    admin_changelist_url_name = None
    app_label = None
    entity_name = None
    entity_name_plural = None
    template_name = "admin/processing/dashboard.html"

    @staticmethod
    def _parse_date_range(request):
        """Parse date range from GET params.

        Supports explicit start_date/end_date or legacy days shortcut.
        Returns (start_date, end_date) clamped to valid range.
        """
        today = date.today()
        start_str = request.GET.get("start_date", "")
        end_str = request.GET.get("end_date", "")

        if start_str and end_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                start_date = today - timedelta(days=29)
                end_date = today
        elif request.GET.get("days"):
            try:
                days = int(request.GET["days"])
            except ValueError:
                days = 30
            days = max(1, min(days, 365))
            end_date = today
            start_date = end_date - timedelta(days=days - 1)
        else:
            end_date = today
            start_date = end_date - timedelta(days=29)

        # Clamp
        if end_date > today:
            end_date = today
        if start_date > end_date:
            start_date = end_date

        return start_date, end_date

    @staticmethod
    def _apply_token_filter(queryset, token_param):
        """Filter queryset by API token.

        Args:
            queryset: Base queryset to filter.
            token_param: "" or absent for all, "none" for non-API, or token ID.

        Returns:
            Filtered queryset.
        """
        if not token_param:
            return queryset
        if token_param == "none":
            return queryset.filter(created_by_token__isnull=True)
        try:
            token_id = int(token_param)
            return queryset.filter(created_by_token_id=token_id)
        except (ValueError, TypeError):
            return queryset

    def _get_processing_step_choices(self):
        """Load available processing steps for this model.

        Returns:
            List of (step_name, description) tuples.
        """
        try:
            cp = ContentProcessor()
            cp.model = self.model
            steps = cp.get_available_processing_steps()
            return [(name, step.description) for name, step in steps.items()]
        except (ProcessingError, ValueError):
            return []

    def get(self, request):
        """Render dashboard with date range, token filter, and processing steps."""
        start_date, end_date = self._parse_date_range(request)

        # Base queryset filtered by date range
        base_queryset = self.model.objects.filter(
            created_date__date__gte=start_date,
            created_date__date__lte=end_date,
        )

        # Compute token choices from base queryset (before token filter)
        token_choices = list(
            base_queryset.exclude(created_by_token__isnull=True)
            .values("created_by_token__id", "created_by_token__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Apply token filter
        selected_token = request.GET.get("token", "")
        filtered_queryset = self._apply_token_filter(base_queryset, selected_token)

        # Items per day
        items_per_day = (
            filtered_queryset.annotate(day=TruncDate("created_date"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("-day")
        )

        # Items per API token (only API-created items)
        items_per_token = (
            filtered_queryset.exclude(created_by_token__isnull=True)
            .values(
                "created_by_token__id",
                "created_by_token__name",
                "created_by_token__user__username",
            )
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Summary stats
        total_items = filtered_queryset.count()
        api_created = filtered_queryset.exclude(created_by_token__isnull=True).count()
        pending_approval = filtered_queryset.filter(
            review_status="pending",
            created_by_token__isnull=False,
        ).count()

        # Fill in missing days with zero counts
        items_by_day_dict = {item["day"]: item["count"] for item in items_per_day}
        all_days = []
        current_date = end_date
        while current_date >= start_date:
            all_days.append(
                {
                    "day": current_date,
                    "count": items_by_day_dict.get(current_date, 0),
                }
            )
            current_date -= timedelta(days=1)

        # Processing steps
        processing_steps = self._get_processing_step_choices()

        changelist_url = reverse(self.admin_changelist_url_name)

        context = {
            "title": f"{self.entity_name} Creation Dashboard",
            "app_label": self.app_label,
            "entity_name": self.entity_name,
            "entity_name_plural": self.entity_name_plural,
            "changelist_url": changelist_url,
            "start_date": start_date,
            "end_date": end_date,
            "items_per_day": all_days,
            "items_per_token": items_per_token,
            "total_items": total_items,
            "api_created": api_created,
            "pending_approval": pending_approval,
            "day_options": [7, 14, 30, 60, 90, 180, 365],
            "selected_token": selected_token,
            "token_choices": token_choices,
            "processing_steps": processing_steps,
        }

        return render(request, self.template_name, context)

    def post(self, request):
        """Handle batch processing action on selected dates."""
        selected_dates_raw = request.POST.getlist("selected_dates")
        processing_step_name = request.POST.get("processing_step", "")
        token_param = request.POST.get("token", "")

        if not selected_dates_raw:
            messages.error(request, "No dates selected for batch processing.")
            return redirect(request.get_full_path())

        if not processing_step_name:
            messages.error(request, "No processing step selected.")
            return redirect(request.get_full_path())

        # Parse dates
        date_objects = []
        for d in selected_dates_raw:
            try:
                date_objects.append(datetime.strptime(d, "%Y-%m-%d").date())
            except ValueError:
                continue

        if not date_objects:
            messages.error(request, "No valid dates in selection.")
            return redirect(request.get_full_path())

        # Load processing step
        try:
            cp = ContentProcessor()
            cp.model = self.model
            steps = cp.get_available_processing_steps()
        except (ProcessingError, ValueError) as e:
            messages.error(request, f"Failed to load processing steps: {e}")
            return redirect(request.get_full_path())

        if processing_step_name not in steps:
            messages.error(
                request,
                f"Unknown processing step: {processing_step_name}",
            )
            return redirect(request.get_full_path())

        step = steps[processing_step_name]

        # Build queryset
        queryset = self.model.objects.filter(created_date__date__in=date_objects)
        queryset = self._apply_token_filter(queryset, token_param)

        # Execute processing step
        success_count = 0
        error_count = 0
        last_error = None

        for item in queryset.iterator():
            try:
                step.process(item)
                item.save()
                success_count += 1
            except ProcessingError as e:
                error_count += 1
                last_error = e

        entity = self.entity_name.lower()
        if error_count > 0:
            messages.warning(
                request,
                f"Processing completed with errors. "
                f"Success: {success_count}, Errors: {error_count}. "
                f"Last error: {last_error}",
            )
        else:
            messages.success(
                request,
                f"Processing completed successfully. {success_count} {entity}(s) processed.",
            )

        return redirect(request.get_full_path())
