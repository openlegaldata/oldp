"""Custom admin views for court statistics dashboard."""

from oldp.apps.courts.models import Court
from oldp.apps.processing.admin_views import CreationDashboardView


class CourtCreationDashboardView(CreationDashboardView):
    """Dashboard showing court creation statistics with filtering and batch processing."""

    model = Court
    admin_changelist_url_name = "admin:courts_court_changelist"
    app_label = "courts"
    entity_name = "Court"
    entity_name_plural = "Courts"
