import datetime
import logging

from django.http import JsonResponse
from django.utils.translation import ugettext_lazy as _, ugettext
from haystack.forms import FacetedSearchForm
from haystack.generic_views import FacetedSearchView
from haystack.models import SearchResult
from haystack.query import SearchQuerySet

logger = logging.getLogger(__name__)


class CustomSearchForm(FacetedSearchForm):
    pass

    # month = forms.DateField(required=False)

    # start_date = forms.DateField(required=False)
    # end_date = forms.DateField(required=False)
    #

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        # print(self.data)


    def search(self):
        # First, store the SearchQuerySet received from other processing.
        sqs = super().search()

        if not self.is_valid():
            return self.no_query_found()

        # print(self)

        if 'date__range' in self.data:
            range_str = self.data['date__range'].split(',')
            if len(range_str) == 2:
                from_date = datetime.datetime.strptime(range_str[0], '%Y-%m-%d')
                to_date = datetime.datetime.strptime(range_str[1], '%Y-%m-%d')

                # print(from_date)
                sqs = sqs.filter(date__gte=from_date).filter(date__lte=to_date)

           # print()

    #
    #     # Check to see if a start_date was chosen.
    #     if self.cleaned_data['start_date']:

    #
    #     # Check to see if an end_date was chosen.
    #     if self.cleaned_data['end_date']:
    #         sqs = sqs.filter(pub_date__lte=self.cleaned_data['end_date'])
    #
        return sqs


class CustomSearchView(FacetedSearchView):
    """Custom search view for haystack."""
    form_class = CustomSearchForm
    facet_fields = ['facet_model_name', 'book_code', 'court', 'date']

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
                        print(value)

                    facets[facet_name]['choices'].append({
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

        context.update({
            'title': _('Search') + ' ' + context['query'][:30],
            'search_facets': self.get_search_facets(context),
        })

        return context


def autocomplete_view(request):
    """Stub for auto-complete feature(title for all objects missing)

    Suggestions field type = "completion": "my_suggest_field" : {
                    "type" : "completion"
                },

curl -X PUT "localhost:9200/oldp/_mapping/modelresult" -H 'Content-Type: application/json' -d'
{
  "properties": {
    "keyword": {
      "type": "completion"
    }
  }
}
'

curl -X POST "localhost:9200/oldp/modelresult" -H 'Content-Type: application/json' -d'
{
  "keyword" : [ "Gericht", "Amtsgericht", "Urteil", "Urentscheidung", "gerichtsentscheidung" ]
}
'


curl -X POST "localhost:9200/oldp/modelresult" -H 'Content-Type: application/json' -d'
{
  "keyword" : [ "Germany", "Amsel", "Furt", "Gerry", "Gericht" ]
}
'

curl -X POST "localhost:9200/oldp/modelresult/_bulk?pretty" -H 'Content-Type: application/json' -d'
{ "index": { "_id": 1            }}
{ "title_auto": "das urteil vom amtsgericht wird gesprochen. eine tolle entscheidung."    }
{ "index": { "_id": 2            }}
{ "title_auto": "gerichtsentscheidungen sind german court decisions also entscheide von ureltern." }
'

curl -X GET "localhost:9200/oldp/modelresult/_search?pretty" -H 'Content-Type: application/json' -d'
{
    "query": {
        "match": {
            "title_auto": "ge"
        }
    }
}
'



curl -X GET "localhost:9200/_mapping/_doc"
curl -X GET "localhost:9200/_all/_mapping/_doc"


curl -X POST localhost:9200/oldp/_suggest?pretty -d '
{
  "modelresult" : {
    "text" : "ger",
    "completion" : {
      "field" : "keyword",
      "fuzzy" : {
                "fuzziness" : 2
            }
      }
    }
  }
}'

curl -X GET "localhost:9200/oldp/_analyze" -H 'Content-Type: application/json' -d'
{
  "analyzer": "edgengram_analyzer",
  "text": "quick brown"
}
'
curl -X GET "localhost:9200/oldp/_analyze?pretty" -H 'Content-Type: application/json' -d'
{
  "analyzer" : "edgengram_analyzer",
  "text" : "Recommend questions get too fulfilled. He fact in we case miss sake. Entrance be throwing he do blessing"
}'


curl -X POST "localhost:9200/oldp/_search?pretty" -H 'Content-Type: application/json' -d'
{
    "suggest": {
        "modelresult-suggest" : {
            "prefix" : "urt",
            "completion" : {
                "field" : "keyword"
            }
        }
    }
}
'


    """
    suggestions_limit = 5
    sqs = SearchQuerySet().autocomplete(court_name_auto=request.GET.get('q', ''))

    print(sqs.query)

    for result in sqs:  # type: SearchResult
        print(result.object)
        print(result.title)

    suggestions = [result.title for result in sqs]

    return JsonResponse({
        'results': suggestions
    })
