"""Frontend views for case statistics pages.

Each view renders a template shell; JavaScript fetches data from the
stats API and renders charts + tables client-side.
"""

from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from oldp.apps.courts.models import State


class StatsBaseView(TemplateView):
    """Base view for all stats pages."""

    api_endpoint = ""
    page_key = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "nav": "cases",
                "title": self.title,
                "api_base_url": reverse("case-stats-list"),
                "api_endpoint": self.api_endpoint,
                "page_key": self.page_key,
                "stats_section": True,
            }
        )
        return context


class StatsOverviewView(StatsBaseView):
    """Overview page with total cases over time."""

    template_name = "cases/stats/overview.html"
    title = _("Case Statistics")
    api_endpoint = ""
    page_key = "overview"


class StatsByCountryView(StatsBaseView):
    """Cases grouped by country."""

    template_name = "cases/stats/by_country.html"
    title = _("Cases by Country")
    api_endpoint = "by_country/"
    page_key = "by_country"


class StatsByStateView(StatsBaseView):
    """Cases grouped by state."""

    template_name = "cases/stats/by_state.html"
    title = _("Cases by State")
    api_endpoint = "by_state/"
    page_key = "by_state"


class StatsByCourtView(StatsBaseView):
    """Cases grouped by court (requires state filter)."""

    template_name = "cases/stats/by_court.html"
    title = _("Cases by Court")
    api_endpoint = "by_court/"
    page_key = "by_court"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["states"] = State.objects.all().order_by("name")
        return context


class StatsBySourceView(StatsBaseView):
    """Cases grouped by data source. Staff-only — see CaseStatsViewSet.by_source.

    Anonymous and non-staff users get 403 (rendered directly so the
    project-wide handler403 — which returns 401 — is bypassed). The
    sidebar nav link is hidden for non-staff via the template.
    """

    template_name = "cases/stats/by_source.html"
    title = _("Cases by Source")
    api_endpoint = "by_source/"
    page_key = "by_source"

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return HttpResponseForbidden("Staff-only page.")
        return super().dispatch(request, *args, **kwargs)
