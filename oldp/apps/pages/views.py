from django.contrib.flatpages import views as flatpages_views
from django.shortcuts import render

from oldp.apps.pages.renderer import PageNotFound, render_page


def page_view(request, slug):
    """Serve ``/pages/<slug>/`` from a markdown file.

    If no markdown file exists for the slug, fall back to a database flatpage at
    ``/<slug>/`` so legacy flatpages (e.g. ``/api/``) keep working through the
    same ``/pages/`` URL space. Unknown slugs raise 404 via the flatpage view.
    """
    try:
        page = render_page(slug)
    except PageNotFound:
        return flatpages_views.flatpage(request, url=f"/{slug}/")
    return render(request, "pages/detail.html", {"page": page, "title": page["title"]})
