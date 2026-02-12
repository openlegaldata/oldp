"""Custom admin views for case statistics dashboard."""

from oldp.apps.cases.models import Case
from oldp.apps.processing.admin_views import CreationDashboardView


class CaseCreationDashboardView(CreationDashboardView):
    """Dashboard showing case creation statistics with filtering and batch processing."""

    model = Case
    admin_changelist_url_name = "admin:cases_case_changelist"
    app_label = "cases"
    entity_name = "Case"
    entity_name_plural = "Cases"
