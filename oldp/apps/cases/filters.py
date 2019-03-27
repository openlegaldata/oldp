import django_filters
from dal import autocomplete
from django.conf import settings
from django.db import models
from django.forms import HiddenInput, TextInput
from django.forms.widgets import NumberInput
from django.utils.translation import ugettext_lazy as _
from django_filters import FilterSet
from django_filters.rest_framework import FilterSet as RESTFilterSet

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court, State
from oldp.apps.laws.models import Law
from oldp.apps.lib.filters import LazyOrderingFilter
from oldp.apps.lib.widgets import CheckboxLinkWidget, BootstrapDateRangeWidget, \
    VisibleIfSetWidget


class BaseCaseFilter(FilterSet):
    """
    Generic filter for cases (used for front-end and API)
    """
    court = django_filters.ModelChoiceFilter(
        field_name='court',
        label=_('Court'),
        queryset=Court.objects.all().only('id', 'name'),
    )

    court__state = django_filters.ModelChoiceFilter(
        field_name='court__state',
        queryset=State.objects.all().only('id', 'name'),
        label=_('State'),
    )

    has_reference_to_law = django_filters.NumberFilter(
        field_name='has_reference_to_law',
        method='filter_has_reference_to_law',
        label=_('Has reference to'),
        widget=VisibleIfSetWidget(queryset=Law.objects.select_related('book').defer(*Law.defer_fields_list_view), attrs={
            'field_label': _('Has reference to')
        }),
    )

    court__slug = django_filters.CharFilter()
    court__jurisdiction = django_filters.ChoiceFilter(
        label=_('Jurisdiction'),
        choices=[(name, name) for name in settings.COURT_JURISDICTIONS.keys()],
        widget=CheckboxLinkWidget(
            attrs={
                'class': 'checkbox-links'
            }
        )
    )
    court__level_of_appeal = django_filters.ChoiceFilter(
        label=_('Level of Appeal'),
        choices=[(name, name) for name in settings.COURT_LEVELS_OF_APPEAL.keys()],
        widget=CheckboxLinkWidget(
            attrs={
                'class': 'checkbox-links'
            }
        )
    )

    date = django_filters.DateFromToRangeFilter(
        label=_('Published on'),
        widget=BootstrapDateRangeWidget(
            attrs={
                'class': 'date-picker form-control'
            }
        )
    )
    slug = django_filters.CharFilter()
    file_number = django_filters.CharFilter()
    ecli = django_filters.CharFilter()

    def filter_has_reference_to_law(self, queryset, name, value):
        """
        Filter depending on references (currently only with URL)
        """
        return queryset.filter(casereferencemarker__referencefromcase__reference__law_id=value).distinct()


class CaseFilter(BaseCaseFilter):
    """Front-end filters"""
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

        # Set front-end widgets

        # Unset fields (remove these filters from URL-params)
        del self.filters['file_number']
        del self.filters['ecli']
        del self.filters['slug']

        # Hidden widgets
        for field_name in ['court__slug']:
            self.filters.get(field_name).field.widget = HiddenInput()

        # Extra widgets
        self.filters.get('court').field.widget = autocomplete.ModelSelect2(
                url='courts:autocomplete',
                attrs={
                    'data-placeholder': _('Court'),
                }
            )

        self.filters.get('court__state').field.widget = autocomplete.ModelSelect2(
                url='courts:state_autocomplete',
                attrs={
                    'data-placeholder': _('State'),
                },
            )
        # self.filters.get('has_reference_to_law').field.widget = VisibleIfSetInput(model=Law, model_related='book')


class CaseAPIFilter(RESTFilterSet, BaseCaseFilter):
    court = django_filters.NumberFilter()  # Choice list would be too large for regular choice field

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # No fancy widgets
        self.filters.get('court__jurisdiction').field.widget = TextInput()
        self.filters.get('court__level_of_appeal').field.widget = TextInput()
        self.filters.get('has_reference_to_law').field.widget = NumberInput()



