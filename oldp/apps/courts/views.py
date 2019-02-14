from dal import autocomplete
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django.views.generic import ListView

from oldp.apps.cases.models import Case
from oldp.apps.courts.filters import CourtFilter
from oldp.apps.courts.models import *
from oldp.apps.lib.views import SortableFilterView, SortableColumn
from oldp.utils.limited_paginator import LimitedPaginator


class CourtListView(SortableFilterView):
    filterset_class = CourtFilter
    paginate_by = settings.PAGINATE_BY

    columns = [
        SortableColumn(
            label=_('Court title'),
            field_name='name',
            sortable=True
        ),
        SortableColumn(
            label=_('ECLI code'),
            field_name='ecli',
            sortable=False,  # Only filter fields are sortable
            css_class='text-nowrap d-none d-md-table-cell'
        ),
        SortableColumn(
            label=_('State'),
            field_name='state__name',
            sortable=True,
            css_class='text-nowrap d-none d-md-table-cell'
        ),
    ]

    def get_queryset(self):
        return Court.objects.all().select_related('city', 'state').order_by('name').defer(*Court.defer_fields_list_view)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'nav': 'courts',
            'title': _('Courts'),
            'filter_data': self.get_filterset_kwargs(self.filterset_class)['data'],
        })
        return context


class CourtCasesListView(ListView):
    template_name = 'courts/cases_list.html'
    model = Case
    paginator_class = LimitedPaginator
    paginate_by = settings.PAGINATE_BY
    court = None  # type: Court

    def dispatch(self, request, *args, **kwargs):
        # Set court based on slug
        self.court = get_object_or_404(Court, slug=kwargs['court_slug'])

        return super(CourtCasesListView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Get cases that belong to court
        queryset = Case.get_queryset(self.request)\
            .select_related('court')\
            .defer(*Case.defer_fields_list_view)\
            .filter(court=self.court)\
            .order_by('-date')

        return queryset

    def get_context_data(self, **kwargs):
        context = super(CourtCasesListView, self).get_context_data(**kwargs)

        print(context['paginator'].count)

        context.update({
            'nav': 'courts',
            'title': self.court.name,
            'court': self.court
        })
        return context


class CourtAutocomplete(autocomplete.Select2QuerySetView):
    def get_result_label(self, item):
        return item.name

    def get_queryset(self):
        qs = Court.objects.all().order_by('name').defer(*Court.defer_fields_list_view)

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs


class StateAutocomplete(autocomplete.Select2QuerySetView):
    def get_result_label(self, item):
        return item.name

    def get_queryset(self):
        qs = State.objects.all().order_by('name')

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs
