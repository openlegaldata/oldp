import json
import logging
import os
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.db.models import Model
from django.forms import model_to_dict
from elasticsearch import NotFoundError
from elasticsearch.client import IndicesClient, Elasticsearch

from oldp.apps.backend.processing import ProcessingError
from oldp.apps.backend.processing.processing_steps.post import PostProcessingStep
from oldp.apps.search.models import SearchableContent

logger = logging.getLogger(__name__)


class SendToES(PostProcessingStep):
    """Populate content after processing to Elasticsearch

    content type needs to be SearchableContent

    """

    # TODO upsert queries?

    # ES Settings
    # self.es_url_heroku = 'https://se8cnkis:ycn8j4g2j4kl3m90@elm-7226066.us-east-1.bonsaisearch.net'
    es_url = settings.ES_URL
    es_scheme = 'http'
    es_host = 'localhost'
    es_port = 9200

    es = None
    es_ic = None
    es_enabled = True
    es_index = 'oldp'
    es_type = None
    es_index_settings = None

    # Bulk
    items_per_batch = 30
    bulk_data = ''
    bulk_size = 0

    content_types = []  # list SearchableContent

    # Stats
    req_counter = 0
    req_failed_counter = 0
    bulk_ok_counter = 0
    bulk_failed_counter = 0

    def __init__(self):
        super().__init__()

        self.es_index_settings = os.path.join(settings.BASE_DIR, 'oldp/assets/es_index.json')

    @staticmethod
    def set_parser_arguments(parser):
        parser.add_argument('--es', action='store_true', default=False, help='Enables ES post processing step')
        parser.add_argument('--es-url', type=str, default=settings.ES_URL, help='ES url')
        parser.add_argument('--es-setup', action='store_true', default=False,
                            help='Creates index with mapping (Override existing index)')

    def set_es_url(self, url):
        """Parse ES url to extract index name etc."""
        o = urlparse(url)

        self.es_scheme = o.scheme
        self.es_host = o.hostname
        self.es_port = o.port

        p = o.path.split('/')

        if len(p) == 2:
            self.es_index = p[1]
        else:
            raise ProcessingError('Cannot extract index from ES url: %s' % url)

        self.es_url = '%s://%s:%i' % (self.es_scheme, self.es_host, self.es_port)

    def process(self, content):
        """Loop over all processed docs and perform bulk indexing"""

        for doc in content:  # type: SearchableContent
            if isinstance(doc, SearchableContent):
                self.bulk_index(doc, doc_id=doc.get_id(), doc_type=doc.es_type)
            else:
                logger.error('ES documents needs to be from type: SearchableContent')

        self.send_data_to_es()
        self.log_stats()

    def get_es(self):
        if self.es is None:
            ssl_url = self.es_url.startswith('https')

            if ssl_url:
                # TODO add valid cert in ES setup
                logger.warning('ES does not use cert validation.')

            self.es = Elasticsearch([self.es_url], verify_certs=False)

        return self.es

    def get_es_ic(self):
        if self.es_ic is None:
            self.es_ic = IndicesClient(client=self.get_es())

        return self.es_ic

    def empty_content(self):
        try:
            for content_type in self.content_types:  # type: SearchableContent
                self.get_es().delete_by_query(index=self.es_index, body='{ "query": { "match_all": {} } }',
                                              doc_type=content_type.es_type)
                logger.debug('All documents deleted with type=%s' % content_type.es_type)

        except ConnectionError:
            logger.error('Could not connect to ES: %s' % self.es_url)
            exit(1)

    def setup_index(self, path_to_settings=None):
        """ Create new Elasticsearch index (override existing index)

        :param path_to_settings: If is None default settings file is used
        :return:
        """
        try:

            if path_to_settings is None:
                path_to_settings = self.es_index_settings

            logger.debug('Reading ES index settings from: %s' % path_to_settings)

            with open(path_to_settings, 'r') as data_file:
                index_body = data_file.read().replace('\n', '')

            try:
                self.get_es_ic().delete(index=self.es_index)
            except NotFoundError:
                logger.warning('Index does not exist yet: %s' % self.es_index)

            res = self.get_es_ic().create(index=self.es_index, body=index_body)

            logger.info('Index created: %s' % res)

        except ConnectionError:
            logger.error('Could not connect to ES: %s' % self.es_url)
            exit(1)

    def get_es_bulk_url(self):
        return self.es_url + '/_bulk'

    def bulk_index(self, doc, doc_type=None, doc_index=None, doc_id=None):
        if doc_type is None:
            if self.es_type is None:
                raise ProcessingError('No ES document type defined')
            doc_type = self.es_type

        if doc_index is None:
            doc_index = self.es_index

        action = {'index': {'_index': doc_index, '_type': doc_type}}

        if doc_id is not None:
            action['index']['_id'] = doc_id

        self.bulk_data += json.dumps(action) + '\n'

        # Convert Django model
        if isinstance(doc, Model):
            logger.debug('Convert Django model: %s' % doc)

            # Should some fields be excluded?
            if hasattr(doc, 'es_fields_exclude'):
                doc_dict = model_to_dict(doc, exclude=doc.es_fields_exclude)
            else:
                doc_dict = model_to_dict(doc)

            # Has pre_index signal?
            pre_index = getattr(doc, "pre_index", None)
            if callable(pre_index):
                # logger.debug('Calling pre_index signal for model')
                pre_index(doc_dict)

            # if 'revision_date' in doc:
            #     del doc['revision_date']
            #     pass

            doc_str = json.dumps(doc_dict)

        elif isinstance(doc, dict):
            doc_str = json.dumps(doc)
        else:
            raise ProcessingError('Cannot transform to JSON: %s' % doc)

        self.bulk_data += doc_str + '\n'

        self.bulk_size += 1

        if self.bulk_size >= self.items_per_batch:
            self.send_data_to_es()

    def send_data_to_es(self, data=None):
        """
        Send data to ES server
        :param data: String
        """
        if not self.es_enabled:
            return

        logger.debug('Sending bulk request. Documents %i ' % self.bulk_size)

        if data is None:
            data = self.bulk_data

        self.bulk_data = ''
        self.bulk_size = 0

        if len(data) < 1:
            logger.warning('No bulk data to send')
            return
        try:
            # logger.debug('Bulk data: %s' % data)
            r = requests.put(self.get_es_bulk_url(), data=data)

            # logger.debug('ES response: %s' % r.text)

            # TODO Parse response
            self.parse_bulk_response(r.json())

        except requests.exceptions.RequestException as e:
            if self.req_failed_counter is not None:
                self.req_failed_counter += 1
            logger.error("Failed to send bulk: " + str(e))
            return False
        if r.status_code != 200:
            logger.error('Failed to send bulk (ES error, status=%i): %s' % (r.status_code, r.text))
            logger.debug('Bulk data: %s' % data)
            if self.req_failed_counter is not None:
                self.req_failed_counter += 1
            r.close()
            return False

        # self.parse_response(r)
        # logger.debug(r.text)

        if self.req_counter is not None:
            self.req_counter += 1
        return True

    def parse_bulk_response(self, res: dict):

        for item in res['items']:
            # TODO Other actions
            if 'index' in item and item['index']['status'] == 201:
                self.bulk_ok_counter += 1
            else:
                self.bulk_failed_counter += 1

    def log_stats(self):
        logger.info(' - requests %i (failed: %i)' % (self.req_counter, self.req_failed_counter))
        logger.info(' - bulk items %i (failed %i)' % (self.bulk_ok_counter, self.bulk_failed_counter))

