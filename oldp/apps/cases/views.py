from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import ugettext_lazy as _

from oldp.apps.cases.filters import CaseFilter
from oldp.apps.cases.models import Case
from oldp.apps.lib.apps import Counter
from oldp.apps.lib.views import SortableFilterView, SortableColumn
from oldp.utils.cache_per_user import cache_per_user


class CaseFilterView(SortableFilterView):
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
        return Case.get_queryset(self.request).select_related('court')

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
        'content': item.get_content_as_html(request),
        'annotation_labels': item.get_annotation_labels(request) if request.user.is_staff else None,
        'line_counter': Counter(),
        'nav': 'cases',
    })


def short_url_view(request, pk):
    item = get_object_or_404(Case.get_queryset(request), pk=pk)

    return redirect(item.get_absolute_url(), permanent=True)


def annotate_view(request):
    return render(request, 'annotate.html', {})
