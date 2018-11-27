from django.conf import settings
from django.http import QueryDict
from django_filters.views import FilterView

from oldp.apps.lib.templatetags.qstring import qstring_set
from oldp.utils.cache_per_user import cache_per_user


class SortableColumn(object):
    order = None
    url = None  # type: str

    def __init__(self, label, field_name, sortable):
        self.label = label
        self.field_name = field_name
        self.sortable = sortable


class SortableFilterView(FilterView):
    columns = []  # type: List[SortableColumn]

    def dispatch(self, *args, **kwargs):
        return cache_per_user(settings.CACHE_TTL)(super().dispatch)(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_data = self.get_filterset_kwargs(self.filterset_class)['data']  # type: QueryDict

        for i, col in enumerate(self.columns):
            # set url, order,
            if col.sortable:
                field_name = col.field_name

                if filter_data.get('o') == field_name:
                    self.columns[i].order = 'asc'
                    self.columns[i].url = qstring_set(filter_data.urlencode(), 'o=-' + field_name)
                elif  filter_data.get('o') == '-' + field_name:
                    self.columns[i].order = 'desc'
                    self.columns[i].url = qstring_set(filter_data.urlencode(), 'o=' + field_name)
                else:
                    self.columns[i].order = ''
                    self.columns[i].url = qstring_set(filter_data.urlencode(), 'o=' + field_name)

        context.update({
            'columns': self.columns
        })

        return context

    def get_filterset_kwargs(self, filterset_class):
        kwargs = super().get_filterset_kwargs(filterset_class)

        if 'data' in kwargs and kwargs['data'] is None:
            # Set default values
            # print(kwargs['data'])
            kwargs['data'] = QueryDict('court=&o=-date')
        elif kwargs['data']:
            # Dirty hack: Set default
            kwargs['data'] = QueryDict(kwargs['data'].urlencode(), mutable=True)
            kwargs['data'].setdefault('o', '-date')
            pass

        return kwargs
