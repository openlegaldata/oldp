import datetime
import logging

from django.http import JsonResponse
from django.utils.translation import ugettext_lazy as _, ugettext
from haystack.forms import FacetedSearchForm
from haystack.generic_views import FacetedSearchView
from haystack.query import SearchQuerySet

logger = logging.getLogger(__name__)


class CustomSearchForm(FacetedSearchForm):
    """
    Our custom search form for facet search with haystack
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def search(self):
        # First, store the SearchQuerySet received from other processing.
        sqs = super().search()

        if not self.is_valid():
            return self.no_query_found()

        # Custom date range filter
        # TODO can this be done with native-haystack?
        if 'start_date' in self.data:
            try:
                sqs = sqs.filter(date__gte=datetime.datetime.strptime(self.data.get('start_date'), '%Y-%m-%d'))
            except ValueError:
                logger.error('Invalid start_date')

        if 'end_date' in self.data:
            try:
                sqs = sqs.filter(date__lte=datetime.datetime.strptime(self.data.get('end_date'), '%Y-%m-%d'))
            except ValueError as e:
                logger.error('Invalid end_date')

        return sqs


class CustomSearchView(FacetedSearchView):
    """Custom search view for haystack."""
    form_class = CustomSearchForm
    facet_fields = [
        'facet_model_name',

        # Law facets
        'book_code',

        # Case facets
        'decision_type',
        'court',
        'court_jurisdiction',
        'court_level_of_appeal',
        'date'
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.date_facet(
            'date',
            start_date=datetime.date(2009, 6, 7),
            end_date=datetime.datetime.now(),
            gap_by='month',
            # gap_amount=1,
        )
        return qs

    def get_search_facets(self, context):
        """Convert haystack facets to make it easier to build a nice facet sidebar"""
        selected_facets = {}
        qs_facets = self.request.GET.getlist("selected_facets")

        for qp in qs_facets:
            tmp = qp.split('_exact:')

            selected_facets[tmp[0]] = tmp[1]

        facets = {}

        if 'fields' in context['facets']:
            for facet_name in context['facets']['fields']:
                # if self.request.GET[facet_name]
                facets[facet_name] = {
                    'name': facet_name,
                    'selected': facet_name in selected_facets,
                    'choices': []
                }

                # All choices
                for facet_choices in context['facets']['fields'][facet_name]:
                    value, count = facet_choices
                    selected = facet_name in selected_facets and selected_facets[facet_name] == value
                    url_param = facet_name + '_exact:%s' % value
                    qs = self.request.GET.copy()

                    if selected:
                        # Remove current facet from url
                        _selected_facets = []
                        for f in qs.getlist('selected_facets'):
                            if f != url_param:
                                _selected_facets.append(f)

                        del qs['selected_facets']
                        qs.setlist('selected_facets', _selected_facets)

                    else:
                        # Add facet to url
                        qs.update({
                            'selected_facets': url_param
                        })

                    # Filter links should not have pagination
                    if 'page' in qs:
                        del qs['page']

                    if facet_name == 'facet_model_name':
                        value = ugettext(value)

                    facets[facet_name]['choices'].append({
                        'facet_name': facet_name,
                        'value': value,
                        'count': count,
                        'selected': selected,
                        'url': '?' + qs.urlencode(),
                    })

                # Remove empty facets
                if not facets[facet_name]['choices']:
                    del facets[facet_name]

        return facets

    def get_context_data(self, *args, **kwargs):
        context = super(CustomSearchView, self).get_context_data(**kwargs)
        date_facets = {}

        if 'dates' in context['facets'] and 'date' in context['facets']['dates']:  # we assume that dates are already sorted
            dates = context['facets']['dates']['date']

            if len(dates) > 1:
                fmt = '%Y-%m-%d'
                date_facets = {
                    'start_date': dates[0][0].strftime(fmt),
                    'end_date': dates[-1][0].strftime(fmt),
                    'items': [{'date': date.strftime(fmt), 'count': count} for date, count in dates],
                }

        context.update({
            'title': _('Search') + ' ' + context['query'][:30],
            'search_facets': self.get_search_facets(context),
            'date_facets': date_facets,
        })

        return context


def autocomplete_view(request):
    """Stub for auto-complete feature(title for all objects missing)

    """
    suggestions_limit = 5
    sqs = SearchQuerySet().autocomplete(title=request.GET.get('q', ''))[:suggestions_limit]

    # for result in sqs:  # type: SearchResult
    #     print(result.object)
    #     print(result.title)

    suggestions = [result.title for result in sqs]

    return JsonResponse({
        'results': suggestions
    })
