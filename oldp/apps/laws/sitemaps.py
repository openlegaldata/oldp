from django.contrib.sitemaps import GenericSitemap

from oldp.apps.laws.models import Law


class LawSitemap(GenericSitemap):

    def __init__(self):
        super().__init__({
            'queryset': Law.objects.select_related('book').filter(book__latest=True).order_by('-updated_date'),
            'date_field': 'updated_date'
        }, priority=0.9)
