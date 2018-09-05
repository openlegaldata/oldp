import logging
import string

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import Http404
from django.shortcuts import render, get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.cache import cache_page

from oldp.apps.laws.models import Law, LawBook

logger = logging.getLogger(__name__)


@cache_page(settings.CACHE_TTL)
def view_index(request, char=None):

    page = request.GET.get('page')
    items = LawBook.objects.filter(latest=True)  #.values('slug', 'title', 'code').annotate(n=models.Count('slug'))

    if char is not None and len(char) == 1:
        char = str(char).lower()
        items = items.filter(slug__startswith=char)  # Case sensitive filtering

        top_items = []
    else:
        items = items.all()
        top_items = items.order_by('-order')[:5]

    items = items.order_by('title')

    paginator = Paginator(items, 40)

    try:
        items = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        items = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        items = paginator.page(paginator.num_pages)

    return render(request, 'laws/index.html', {
        'nav': 'laws',
        'items': items,
        'top_items': top_items,
        'char': char,
        'chars':  list(string.ascii_lowercase),  # TODO as function
        'title': _('Laws')
    })


def get_latest_law_book(book_slug):
    """Law book by slug and latest=true (logs warning if multiple instances exist)"""
    candidates = LawBook.objects.filter(slug=book_slug, latest=True)

    if len(candidates) == 0:
        raise Http404()
    else:
        # This should usually not happen, but better check it...
        if len(candidates) > 1:
            logger.warning('Book has more than one instance with latest=true: {}'.format(book_slug))

        return candidates[0]


def get_law_book(request, book_slug):
    """Law book by slug and optional revision_date"""
    revision_date = request.GET.get('revision_date')

    if revision_date:
        try:
            return LawBook.objects.get(slug=book_slug, revision_date=revision_date)
        except LawBook.DoesNotExist:
            messages.warning(request, _('The requested revision (%s) was not found. Showing instead the latest revision.' % revision_date))
            return get_latest_law_book(book_slug)
    else:
        return get_latest_law_book(book_slug)


@cache_page(settings.CACHE_TTL)
def view_book(request, book_slug):
    book = get_law_book(request, book_slug)

    items = Law.objects.filter(book=book).select_related('book').order_by('order')

    return render(request, 'laws/book.html', {
        'items': items,
        'book': book,
        'title': book.get_title(),
        'nav': 'laws'
    })


@cache_page(settings.CACHE_TTL)
def view_law(request, law_slug, book_slug):

    book = get_law_book(request, book_slug)
    item = get_object_or_404(Law.objects.select_related('book', 'previous'), slug=law_slug, book=book)

    return render(request, 'laws/law.html', {
        'nav': 'laws',
        'item': item,
        'title': item.get_title()
    })
