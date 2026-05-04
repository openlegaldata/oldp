from django.contrib.sitemaps import GenericSitemap

from oldp.apps.laws.models import Law


class LawSitemap(GenericSitemap):
    def __init__(self):
        # Sitemaps run anonymously: get_queryset(request=None) returns
        # accepted-only, hiding pending/rejected laws from public crawlers.
        super().__init__(
            {
                "queryset": Law.get_queryset()
                .select_related("book")
                .filter(book__latest=True)
                .defer("content", "footnotes")
                .order_by("-updated_date"),
                "date_field": "updated_date",
            },
            priority=0.9,
        )
