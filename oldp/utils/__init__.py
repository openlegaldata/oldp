import logging.config
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def find_from_mapping(haystack, mapping, mapping_list=False, default=None):
    """
    Finds a word based on mapping, e.g. court code search:

    Verwaltungsgericht -> VG

    :param self:
    :param haystack:
    :param mapping:
    :param mapping_list:
    :param default:
    :return:
    """
    for needle in mapping:
        # print(needle)
        if re.search(r'\b' + re.escape(needle) + r'\b', haystack, flags=re.IGNORECASE):
            if mapping_list:
                return needle
            else:
                return mapping[needle]
    return default


def get_elasticsearch_settings_from_url(es_url):
    es_scheme, es_host, es_port, es_index = get_elasticsearch_from_url(es_url)
    return {
        'scheme': es_scheme,
        'host': es_host,
        'port': es_port,
        'index': es_index,
        'use_ssl': es_scheme == 'https',
        'urls': [es_url]
    }


def get_elasticsearch_from_url(es_url):
    """Extract elasticsearch settings from url

    :param es_url: Elasticsearch URL
    :return: es_scheme, es_host, es_port, es_index
    """
    o = urlparse(es_url)

    es_scheme = o.scheme
    es_host = o.hostname
    es_port = o.port

    p = o.path.split('/')

    if len(p) == 2:
        es_index = p[1]
    else:
        raise ValueError('Cannot extract index from ES url: %s' % es_url)

    return es_scheme, es_host, es_port, es_index
