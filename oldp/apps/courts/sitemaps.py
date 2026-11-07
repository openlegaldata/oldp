from django.contrib.sitemaps import GenericSitemap

from oldp.apps.courts.models import Court


class CourtSitemap(GenericSitemap):
    """Accepted courts, rendered by ``manage.py generate_sitemaps``."""

    def __init__(self):
        super().__init__(
            {
                "queryset": Court.objects.filter(review_status="accepted")
                .only("pk", "slug", "updated_date")
                .order_by("pk"),
                "date_field": "updated_date",
            },
            priority=0.6,
        )
