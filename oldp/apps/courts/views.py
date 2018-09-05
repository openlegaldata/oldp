from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django.views.generic import ListView

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import *


class CourtCasesListView(ListView):
    template_name = 'courts/cases_list.html'
    model = Case
    paginate_by = settings.PAGINATE_BY
    court = None  # type: Court

    def dispatch(self, request, *args, **kwargs):
        # Set court based on slug
        self.court = get_object_or_404(Court, slug=kwargs['court_slug'])

        return super(CourtCasesListView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Get cases that belong to court
        queryset = Case.get_queryset(self.request).filter(court_id=self.court.pk).order_by('date')

        return queryset

    def get_context_data(self, **kwargs):
        context = super(CourtCasesListView, self).get_context_data(**kwargs)

        context.update({
            'nav': 'cases',
            'title': self.court.name,
            'court': self.court
        })
        return context


class CourtListView(ListView):
    model = Court
    paginate_by = settings.PAGINATE_BY
    states = State.objects.all()

    def get_queryset(self):
        queryset = Court.objects.all()

        # Filter by state if slug is provided
        if 'state_slug' in self.kwargs and self.kwargs['state_slug'] is not None:
            queryset = queryset.filter(state__slug=self.kwargs['state_slug'])

        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super(CourtListView, self).get_context_data(**kwargs)

        if 'state_slug' in self.kwargs:
            state_slug = self.kwargs['state_slug']
        else:
            state_slug = None

        context.update({
            'nav': 'cases',
            'title': _('Courts'),
            'states': self.states,
            'state_slug': state_slug
        })

        return context

