import django_filters
from dal import autocomplete
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_filters import FilterSet

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court, State
from oldp.apps.lib.filters import LazyOrderingFilter


class CaseFilter(FilterSet):
    court = django_filters.ModelChoiceFilter(
        field_name='court',
        label=_('Court'),
        queryset=Court.objects.all().order_by('name'),
        widget=autocomplete.ModelSelect2(
            url='courts:autocomplete',
            attrs={
                'data-placeholder': _('Court'),
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
                'data-placeholder': _('State'),
            },
        ),
    )

    o = LazyOrderingFilter(
        fields=(
            ('date', 'date'),
            ('updated_date', 'updated_date'),  # not used in template
            ('file_number', 'file_number'),
        ),
        field_labels={
            'date': _('Publication date'),
            'updated_date': _('Last modified date'),
            'file_number': _('File number'),

        },
        initial='-date',  # is overwritten in SortableFilterView
        # widget=forms.HiddenInput,
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class CaseAPIFilter(FilterSet):
    slug = django_filters.CharFilter()
    file_number = django_filters.CharFilter()
    # court = django_filters.NumberFilter()
    # court__slug = django_filters.CharFilter()

