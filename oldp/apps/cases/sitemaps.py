from django.contrib.sitemaps import GenericSitemap

from oldp.apps.cases.models import Case


class CaseSitemap(GenericSitemap):
    """Accepted cases, rendered by ``manage.py generate_sitemaps``.

    Ordered by pk so the pages stay stable while cases are added or updated
    during a run (``-updated_date`` would shift rows between pages). Only the
    columns the URL and ``lastmod`` need are loaded.
    """

    def __init__(self):
        # Sitemaps run anonymously: get_queryset(request=None) returns
        # accepted-only.
        super().__init__(
            {
                "queryset": Case.get_queryset()
                .only("pk", "slug", "updated_date")
                .order_by("pk"),
                "date_field": "updated_date",
            },
            priority=1.0,
            changefreq="daily",
        )
