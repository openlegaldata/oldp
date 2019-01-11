import django_filters
from django.forms.utils import pretty_name
from django.utils.text import format_lazy
from django.utils.translation import ugettext_lazy as _


class LazyOrderingFilter(django_filters.OrderingFilter):
    def build_choices(self, fields, labels):
        # With lazy translate
        ascending = [
            (param, labels.get(field, _(pretty_name(param))))
            for field, param in fields.items()
        ]
        descending = [
            ('-%s' % param, labels.get('-%s' % param, format_lazy('{} ({})', label, _('descending'))))
            for param, label in ascending
        ]

        # interleave the ascending and descending choices
        return [val for pair in zip(ascending, descending) for val in pair]
