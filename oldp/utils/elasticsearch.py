import logging
from typing import Type

from elasticsearch import Elasticsearch

from oldp.apps.search.models import SearchableContent

logger = logging.getLogger(__name__)

def get_es():
    from django.conf import settings

    return Elasticsearch(settings.ELASTICSEARCH['host'], verify_certs=False)


def delete_elasticsearch_documents(content_type: Type[SearchableContent]):
    from django.conf import settings

    get_es().delete_by_query(index=settings.ELASTICSEARCH['index'], body='{ "query": { "match_all": {} } }',
                                  doc_type=content_type.es_type)
    logger.debug('All documents deleted with type=%s' % content_type.es_type)


