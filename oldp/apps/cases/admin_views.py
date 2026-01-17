"""
Custom admin views for case statistics dashboard.
"""

from datetime import date, timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

from oldp.apps.cases.models import Case


@method_decorator(staff_member_required, name="dispatch")
class CaseCreationDashboardView(View):
    """Dashboard showing case creation statistics."""

    template_name = "admin/cases/dashboard.html"

    def get(self, request):
        # Parse date range from query params
        days = int(request.GET.get("days", 30))

        # Validate days parameter
        if days < 1:
            days = 1
        elif days > 365:
            days = 365

        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        # Get cases in date range
        cases_queryset = Case.objects.filter(
            created_date__date__gte=start_date,
            created_date__date__lte=end_date,
        )

        # Cases per day
        cases_per_day = (
            cases_queryset
            .annotate(day=TruncDate("created_date"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("-day")
        )

        # Cases per API token (only API-created cases)
        cases_per_token = (
            cases_queryset
            .exclude(created_by_token__isnull=True)
            .values(
                "created_by_token__id",
                "created_by_token__name",
                "created_by_token__user__username",
            )
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Summary stats
        total_cases = cases_queryset.count()
        api_created = cases_queryset.exclude(created_by_token__isnull=True).count()
        pending_approval = cases_queryset.filter(
            private=True,
            created_by_token__isnull=False,
        ).count()

        # Fill in missing days with zero counts
        cases_by_day_dict = {item["day"]: item["count"] for item in cases_per_day}
        all_days = []
        current_date = end_date
        while current_date >= start_date:
            all_days.append({
                "day": current_date,
                "count": cases_by_day_dict.get(current_date, 0),
            })
            current_date -= timedelta(days=1)

        context = {
            "title": "Case Creation Dashboard",
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            "cases_per_day": all_days,
            "cases_per_token": cases_per_token,
            "total_cases": total_cases,
            "api_created": api_created,
            "pending_approval": pending_approval,
            "day_options": [7, 14, 30, 60, 90, 180, 365],
        }

        return render(request, self.template_name, context)
