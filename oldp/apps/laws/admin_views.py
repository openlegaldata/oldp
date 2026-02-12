"""Custom admin views for law and lawbook statistics dashboards."""

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.processing.admin_views import CreationDashboardView


class LawCreationDashboardView(CreationDashboardView):
    """Dashboard showing law creation statistics with filtering and batch processing."""

    model = Law
    admin_changelist_url_name = "admin:laws_law_changelist"
    app_label = "laws"
    entity_name = "Law"
    entity_name_plural = "Laws"


class LawBookCreationDashboardView(CreationDashboardView):
    """Dashboard showing law book creation statistics with filtering and batch processing."""

    model = LawBook
    admin_changelist_url_name = "admin:laws_lawbook_changelist"
    app_label = "laws"
    entity_name = "Law Book"
    entity_name_plural = "Law Books"
