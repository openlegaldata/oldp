from django.contrib.sitemaps import GenericSitemap

from oldp.apps.cases.models import Case


class CaseSitemap(GenericSitemap):

    def __init__(self):
        super().__init__({
            'queryset': Case.get_queryset()
                .select_related('court')
                .defer(*Case.defer_fields_list_view)
                .order_by('-updated_date'),
            'date_field': 'updated_date'
        }, priority=1.0, changefreq='daily')
