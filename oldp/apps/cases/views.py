from django.conf import settings
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.shortcuts import render, get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.cache import cache_page

from oldp.apps.cases.apps import is_read_more
from oldp.apps.cases.models import Case
from oldp.apps.lib.apps import Counter


@cache_page(settings.CACHE_TTL)
def index_view(request):
    items = Case.get_queryset(request).select_related('court').order_by('-date')

    paginator = Paginator(items, 50)  # 50 items per page
    page = request.GET.get('page')
    try:
        items = paginator.page(page)
    except PageNotAnInteger:
        items = paginator.page(1)
    except EmptyPage:
        items = paginator.page(paginator.num_pages)

    return render(request, 'cases/index.html', {
        'title': _('Cases'),
        'items': items,
        'nav': 'cases'
    })


@cache_page(settings.CACHE_TTL)
def case_view(request, case_slug):
    item = get_object_or_404(Case.get_queryset(request), slug=case_slug)

    return render(request, 'cases/case.html', {
        'title': item.get_title(),
        'item': item,
        'line_counter': Counter(),
        'nav': 'cases',
        'is_read_more': is_read_more
    })

