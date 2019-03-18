from django.conf import settings
from django.db.models import Count
from django.http import QueryDict
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from oldp.apps.cases.filters import CaseFilter
from oldp.apps.cases.models import Case
from oldp.apps.lib.apps import Counter
from oldp.apps.lib.views import SortableFilterView, SortableColumn
from oldp.utils.cache_per_user import cache_per_user


class CaseFilterView(SortableFilterView):
    """
    Index view for cases with filters + sortable
    """
    filterset_class = CaseFilter
    paginate_by = settings.PAGINATE_BY

    columns = [
        SortableColumn(_('Case'), 'title', False, ''),
        SortableColumn(_('File number'), 'file_number', True, 'text-nowrap d-none d-md-table-cell'),
        SortableColumn(_('Publication date'), 'date', True, 'text-nowrap d-none d-md-table-cell'),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_queryset(self):
        return Case.get_queryset(self.request).select_related('court').defer(*Case.defer_fields_list_view)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Build API-params
        api_params = self.get_filterset_kwargs(self.filterset_class)['data'].copy()  # type: QueryDict

        # Strip page parameter
        if 'page' in api_params:
            del api_params['page']

        context.update({
            'nav': 'cases',
            'title': _('Cases'),
            'filter_data': self.get_filterset_kwargs(self.filterset_class)['data'],

            # URL to API endpoint
            'api_url': reverse('api-root') + 'cases/?' + api_params.urlencode(),

        })
        return context


@cache_per_user(settings.CACHE_TTL)
def case_view(request, case_slug):
    """
    Case detail view
    """
    qs = Case.get_queryset(request).select_related('court').select_related('source')
    item = get_object_or_404(qs, slug=case_slug)

    # Load annotations for staff users
    if request.user.is_staff:
        marker_labels = item.get_markers(request)\
            .values('label__id', 'label__name', 'label__color', 'label__private')\
            .annotate(count=Count('label'))\
            .order_by('count')
        annotation_labels = item.get_annotation_labels(request)
    else:
        marker_labels = None
        annotation_labels = None

    return render(request, 'cases/case.html', {
        'title': item.get_title(),
        'item': item,
        'content': item.get_content_as_html(request),
        'annotation_labels': annotation_labels,
        'marker_labels': marker_labels,
        'line_counter': Counter(),
        'nav': 'cases',
    })


def short_url_view(request, pk):
    """
    Redirects to detail view
    """
    item = get_object_or_404(Case.get_queryset(request).only('slug'), pk=pk)

    return redirect(item.get_absolute_url(), permanent=True)

