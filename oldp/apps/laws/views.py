import logging
import string

from django.conf import settings
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from oldp.apps.laws.models import Law, LawBook
from oldp.utils.cache_per_user import cache_per_role

logger = logging.getLogger(__name__)


DIGIT_FILTER = "0-9"


@cache_per_role(settings.CACHE_TTL)
def view_index(request, char=None):
    page = request.GET.get("page")
    items = LawBook.get_queryset(request).filter(latest=True)
    top_items: list = []

    if char == DIGIT_FILTER:
        # Aggregate quick-link for books whose slug starts with a digit.
        items = items.filter(slug__regex=r"^[0-9]").order_by("slug")
    elif char is not None and len(char) == 1:
        char = str(char).lower()
        items = items.filter(slug__startswith=char).order_by("slug")
    else:
        # On the unfiltered index, surface a curated set of top books and
        # order the rest by most-recently-updated.  The curated set comes
        # from settings.TOP_LAW_BOOKS (a list of slugs); empty list hides
        # the top block entirely (the template already gates on it).
        top_slugs = [s.strip() for s in settings.TOP_LAW_BOOKS if s and s.strip()]
        if top_slugs:
            by_slug = {
                b.slug: b
                for b in LawBook.get_queryset(request).filter(
                    latest=True, slug__in=top_slugs
                )
            }
            # Preserve configured order; silently drop unknown slugs.
            top_items = [by_slug[s] for s in top_slugs if s in by_slug]
        items = items.order_by("-updated_date")

    paginator = Paginator(items, settings.PAGINATE_BY)

    try:
        items = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        items = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        items = paginator.page(paginator.num_pages)

    return render(
        request,
        "laws/index.html",
        {
            "nav": "laws",
            "items": items,
            "top_items": top_items,
            "char": char,
            "chars": list(string.ascii_lowercase) + [DIGIT_FILTER],
            "title": _("Laws"),
        },
    )


def get_latest_law_book(request, book_slug):
    """Law book by slug, resolving the latest revision.

    Prefers the revision flagged ``latest=True``; if none is flagged but the
    book has revisions, falls back to the newest revision (see
    :meth:`LawBook.resolve_latest`) so the book still renders instead of 404ing.
    Logs a warning if multiple revisions are flagged ``latest=True``.
    """
    candidates = LawBook.get_queryset(request).filter(slug=book_slug, latest=True)

    if candidates.count() > 1:
        logger.warning(
            "Book has more than one instance with latest=true: %s", book_slug
        )

    book = LawBook.resolve_latest(LawBook.get_queryset(request), slug=book_slug)

    if book is None:
        logger.info("Law book not found: %s", book_slug)
        raise Http404()

    return book


def get_law_book(request, book_slug):
    """Law book by slug and optional revision_date"""
    revision_date = request.GET.get("revision_date")

    if revision_date:
        try:
            return LawBook.get_queryset(request).get(
                slug=book_slug, revision_date=revision_date
            )
        except LawBook.DoesNotExist:
            logger.debug(
                "Requested revision not found: book=%s, revision_date=%s",
                book_slug,
                revision_date,
            )
            messages.warning(
                request,
                _(
                    "The requested revision (%s) was not found. Showing instead the latest revision."
                    % revision_date
                ),
            )
            return get_latest_law_book(request, book_slug)
    else:
        return get_latest_law_book(request, book_slug)


@cache_per_role(settings.CACHE_TTL)
def view_book(request, book_slug):
    book = get_law_book(request, book_slug)
    section_titles = book.get_sections()
    revision_dates = list(book.get_revision_dates())

    items_qs = (
        Law.get_queryset(request)
        .filter(book=book)
        .select_related("book")
        .defer(*Law.defer_fields_list_view)
        .order_by("order")
    )
    items = list(items_qs)
    for item in items:
        item.display_section = section_titles.get(str(item.order))

    return render(
        request,
        "laws/book.html",
        {
            "items": items,
            "book": book,
            "revision_dates": revision_dates,
            "title": book.get_title(),
            "nav": "laws",
        },
    )


@cache_per_role(settings.CACHE_TTL)
def view_law(request, law_slug, book_slug):
    from oldp.apps.cases.search_indexes import cited_law_token
    from oldp.apps.search.utils import citing_cases_via_es

    book = get_law_book(request, book_slug)
    item = get_object_or_404(
        Law.get_queryset(request).select_related("book", "previous"),
        slug=law_slug,
        book=book,
    )
    revision_dates = list(book.get_revision_dates())

    referencing_cases, referencing_cases_count, referencing_cases_error = (
        citing_cases_via_es("cited_laws", cited_law_token(book.slug, item.slug))
    )
    # Deep link to the full search results, preserving the citation
    # filter — used both by the "Show all N cases ..." pagination link
    # and by the "search is unavailable" fallback message.
    referencing_cases_search_url = (
        reverse("haystack_search")
        + "?"
        + urlencode(
            {
                "cited_law_book": book.slug,
                "cited_law_section": item.slug,
            }
        )
    )

    return render(
        request,
        "laws/law.html",
        {
            "nav": "laws",
            "item": item,
            "title": item.get_title(),
            "revision_dates": revision_dates,
            "referencing_cases": referencing_cases,
            "referencing_cases_count": referencing_cases_count,
            "referencing_cases_error": referencing_cases_error,
            "referencing_cases_search_url": referencing_cases_search_url,
        },
    )
