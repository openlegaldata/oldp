import django_filters
from dal import autocomplete
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_filters import FilterSet

from oldp.apps.courts.models import Court, State
from oldp.apps.lib.filters import LazyOrderingFilter
from oldp.apps.lib.widgets import CheckboxLinkWidget


class CourtFilter(FilterSet):
    state = django_filters.ModelChoiceFilter(
        field_name='state',
        label=_('State'),
        queryset=State.objects.all().order_by('name'),
        widget=autocomplete.ModelSelect2(
            url='courts:state_autocomplete',
            attrs={
                'data-placeholder': _('State'),
            },
        ),
    )
    jurisdiction = django_filters.ChoiceFilter(
        field_name='jurisdiction',
        label=_('Jurisdiction'),
        choices=[(name, name) for name in settings.COURT_JURISDICTIONS.keys()],
        widget=CheckboxLinkWidget(
            attrs={
                'class': 'checkbox-links'
            }
        ),
    )
    level_of_appeal = django_filters.ChoiceFilter(
        field_name='level_of_appeal',
        label=_('Level of Appeal'),
        choices=[(name, name) for name in settings.COURT_LEVELS_OF_APPEAL.keys()],
        widget=CheckboxLinkWidget(
            attrs={
                'class': 'checkbox-links'
            }
        ),
    )
    o = LazyOrderingFilter(
        fields=(
            ('name', 'name'),
            ('state__name', 'state__name'),
        ),
        field_labels={
            'name': _('Court title'),
            'state': _('State'),
        },
        initial='name',
    )

    class Meta:
        model = Court
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
        # self.get_filters()
