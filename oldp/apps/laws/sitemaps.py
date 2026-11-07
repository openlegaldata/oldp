from django.contrib.sitemaps import GenericSitemap

from oldp.apps.laws.models import Law


class LawSitemap(GenericSitemap):
    """Accepted sections of the latest book revisions.

    Rendered by ``manage.py generate_sitemaps``. Ordered by pk for stable
    pages; only the columns the URL and ``lastmod`` need are loaded.
    """

    def __init__(self):
        # Sitemaps run anonymously: get_queryset(request=None) returns
        # accepted-only, hiding pending/rejected laws from public crawlers.
        super().__init__(
            {
                "queryset": Law.get_queryset()
                .select_related("book")
                .filter(book__latest=True)
                .only("pk", "slug", "updated_date", "book__slug")
                .order_by("pk"),
                "date_field": "updated_date",
            },
            priority=0.9,
        )
