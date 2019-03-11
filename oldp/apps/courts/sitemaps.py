from django.contrib.sitemaps import GenericSitemap

from oldp.apps.courts.models import Court


class CourtSitemap(GenericSitemap):
    def __init__(self):
        super().__init__({
            'queryset': Court.objects.all().order_by('-updated_date'),
            'date_field': 'updated_date'
        }, priority=0.6)
