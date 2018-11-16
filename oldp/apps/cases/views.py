import django_filters
from dal import autocomplete
from django import forms
from django.conf import settings
from django.db import models
from django.shortcuts import render, get_object_or_404
from django.utils.translation import ugettext
from django.utils.translation import ugettext_lazy as _
from django_filters import FilterSet

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court, State
from oldp.apps.lib.apps import Counter
from oldp.apps.lib.views import SortableFilterView, SortableColumn
from oldp.utils.cache_per_user import cache_per_user


class CaseFilter(FilterSet):

    court = django_filters.ModelChoiceFilter(
        field_name='court',
        label=_('Court'),
        queryset=Court.objects.all().order_by('name'),
        widget=autocomplete.ModelSelect2(
            url='courts:autocomplete',
            attrs={
                'data-placeholder': '%s: %s' %(ugettext('Court'), ugettext('all')),
            }
        ),
    )
    court__state = django_filters.ModelChoiceFilter(
        field_name='court__state',
        label=_('State'),
        queryset=State.objects.all().order_by('name'),
        widget=autocomplete.ModelSelect2(
            url='courts:state_autocomplete',
            attrs={
                'data-placeholder': '%s: %s' %(ugettext('State'), ugettext('all')),
            },
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    o = django_filters.OrderingFilter(
        fields=(
            ('date', 'date'),
            ('file_number', 'file_number'),
        ),
        field_labels={
            'date': _('Publication date'),
            'file_number': _('File number'),

        },
        initial='-created_date',
        widget=forms.HiddenInput,
    )

    class Meta:
        model = Case
        fields = []
        filter_overrides = {
            models.CharField: {
                'filter_class': django_filters.CharFilter,
                'extra': lambda f: {
                    'lookup_expr': 'icontains',
                },
            },
        }


class CaseFilterView(SortableFilterView):
    filterset_class = CaseFilter
    paginate_by = settings.PAGINATE_BY

    columns = [
        SortableColumn(_('Case'), 'title', False),
        SortableColumn(_('File number'), 'file_number', True),
        SortableColumn(_('Publication date'), 'date', True),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_queryset(self):
        return Case.get_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'nav': 'cases',
            'title': _('Cases'),
            'filter_data': self.get_filterset_kwargs(self.filterset_class)['data'],
        })
        return context


@cache_per_user(settings.CACHE_TTL)
def case_view(request, case_slug):
    item = get_object_or_404(Case.get_queryset(request), slug=case_slug)

    return render(request, 'cases/case.html', {
        'title': item.get_title(),
        'item': item,
        'line_counter': Counter(),
        'nav': 'cases',
    })

