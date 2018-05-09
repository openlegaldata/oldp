import logging
from math import ceil
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import MultiMatch

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law
from oldp.apps.search.models import SearchableContent, SearchQuery

logger = logging.getLogger(__name__)


class Searcher(object):
    PER_PAGE = 10
    MAX_PAGES = 10

    es = None
    es_index = None
    es_use_ssl = False
    es_urls = None
    query = None
    response = None
    took = 0  # Milliseconds for query execution
    hits = None
    total_hits = 0  # Total number of found documents
    page = 1  # Current page
    doc_type = None  # Filter for document type (None = all types)
    models = {
        'law': Law,
        'case': Case,
    }

    def __init__(self, query: str):

        if query is None:
            query = ''

        self.query = query.lower()

    def parse_es_url(self):
        es_url = settings.ES_URL
        self.es_urls = []

        for url in str(es_url).split(','):
            parsed = urlparse(url)

            if parsed.scheme == 'https':
                self.es_use_ssl = True

            self.es_index = parsed.path.replace('/', '')
            self.es_urls.append(parsed.scheme + '://' + parsed.netloc)

        if self.es_index is None:
            raise ValueError('Cannot parse ES url from: {}'.format(es_url))

    def get_es_urls(self):
        if self.es_urls is None:
            self.parse_es_url()
        return self.es_urls

    def get_es_index(self):
        if self.es_index is None:
            self.parse_es_url()
        return self.es_index

    def get_es(self):
        if self.es is None:
            self.es = Elasticsearch(self.es_urls, use_ssl=self.es_use_ssl, verify_certs=False)
        return self.es

    def set_page(self, page):
        if page is None:
            self.page = 1
            return

        try:
            page = int(page)
        except ValueError:
            self.page = 1
            return

        page = max(1, page)
        page = min(self.MAX_PAGES, page)

        self.page = page

    def set_doc_type(self, doc_type):
        if doc_type is not None and doc_type in self.models:
            self.doc_type = doc_type
            logger.debug('Doc type set to: %s' % doc_type)

    def search(self):
        # Define search query
        q = MultiMatch(query=self.query, fields=['title', 'text', 'slug^4', 'book_slug', 'book_code^2'], type='cross_fields')

        logger.debug('ES query: %s' % q)

        s = Search(using=self.get_es(), index=self.get_es_index(), doc_type=self.doc_type)\
            .highlight('text', fragment_size=50)\
            .query(q)

            # .query("match", title=self.query)
            # .filter('term', author=author)

        # s.aggs.bucket('per_tag', 'terms', field='tags') \
        #     .metric('max_lines', 'max', field='lines')

        # Pagination
        page_from = (self.page - 1) * self.PER_PAGE
        page_to = page_from + self.PER_PAGE
        s = s[page_from:page_to]

        self.response = s.execute()
        self.took = self.response._d_['took']
        self.total_hits = self.response._d_['hits']['total']

        # Save query to DB if hits exist
        if self.total_hits > 0:
            query_obj, created = SearchQuery.objects.get_or_create(query=self.query)

            if not created:
                query_obj.counter += 1
                query_obj.save()

    def get_pages(self) -> int:
        return min(self.MAX_PAGES, ceil(self.total_hits / self.PER_PAGE))

    def get_page_range(self):
        return range(1, self.get_pages() + 1)

    def get_results(self):
        # Handle aggregations (for filters)
        # for tag in response.aggregations.per_tag.buckets:
        #     print(tag.key, tag.max_lines.value)

        # logger.debug('ES response length: %s' % len(self.response))
        self.results = []

        # Handle search hits
        for hit in self.response:
            source = hit._d_

            if hit.meta.doc_type in self.models:
                item_model = self.models[hit.meta.doc_type]
                item = item_model().from_hit(source)  # type: SearchableContent
                item.set_search_score(hit.meta.score)

                # logger.debug('Search hit (score=%f): %s' % (item.get_search_score(), item.get_title()))

                if hasattr(hit.meta, 'highlight'):
                    # logger.debug('-- Highlight: %s' % hit.meta.highlight['text'])
                    item.set_search_snippet(' ... '.join(hit.meta.highlight['text']))

                else:
                    # Can happen if match is not in 'text' field
                    # logger.debug('NO highlight')
                    pass

                self.results.append(item)
            else:
                raise ValueError('Search returned unsupported document type: %s' % hit.meta.doc_type)

        # logger.debug('Search results: %s' % self.results)

        return self.results


def search_view(request):

    query = request.GET.get('query') or request.GET.get('q')

    search = Searcher(query)
    search.set_doc_type(request.GET.get('type'))
    search.set_page(request.GET.get('page'))

    try:
        search.search()
        items = search.get_results()

    except ConnectionError:
        items = []
        messages.error(request, _('Search service is currently not available.'))

    return render(request, 'search/index.html', {
        'items': items,
        'title': _('Search') + ' %s' % search.query,
        'searchQuery': search.query,
        'search': search
    })
