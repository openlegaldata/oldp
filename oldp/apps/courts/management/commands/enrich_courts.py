import logging
import urllib

import requests
from django.core.management import BaseCommand

from oldp.apps.backend.processing import ProcessingError
from oldp.apps.courts.models import Court

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Retrieves Wikipedia content to enrich court information'
    language = 'de'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        # parser.add_argument('--output', type=str, default='http://localhost:9200')

        parser.add_argument('--input', type=str)
        # parser.add_argument('--storage', type=str, default='es')

        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--start', type=int, default=0)

        parser.add_argument('--max-lines', type=int, default=-1)

        # parser.add_argument('--post', type=str, default='keep')
        # parser.add_argument('--post-move-path', type=str, default=None)
        #
        parser.add_argument('--verbose', action='store_true', default=False)

        parser.add_argument('--override', action='store_true', default=False, help='Override existing index')
        parser.add_argument('--empty', action='store_true', default=False, help='Empty existing index')

    def get_wikipedia_field(self, query, field='pageid'):
        # Get Wikipedia ID from search API
        res = requests.get('https://' + self.language + '.wikipedia.org/w/api.php?action=query&list=search&srsearch=%s&utf8=&format=json' % query)

        if res.status_code == 200:
            res_obj = res.json()
            if len(res_obj['query']['search']) > 0:
                return res_obj['query']['search'][0][field]
        raise ProcessingError('Cannot get field')

    def get_wikipedia_image(self, query, size=250):
        res = requests.get('https://' + self.language + '.wikipedia.org/w/api.php?action=query&titles=%s&prop=pageimages&format=json&pithumbsize=%i' % (query, size))

        if res.status_code == 200:
            res_obj = res.json()
            # print(res_obj['query']['pages'])
            for p in res_obj['query']['pages']:
                if 'thumbnail' in res_obj['query']['pages'][p]:
                    return res_obj['query']['pages'][p]['thumbnail']['source']
        raise ProcessingError('Cannot get image')

    def get_wikipedia_extract(self, query):
        res = requests.get('https://' + self.language + '.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&exintro=&explaintext=&titles=%s' % query)

        if res.status_code == 200:
            res_obj = res.json()
            for p in res_obj['query']['pages']:
                return res_obj['query']['pages'][p]['extract']
        raise ProcessingError('Cannot get extract')

    def enrich_court(self, item: Court):
        if item.wikipedia_title is None:
            item.wikipedia_title = self.get_wikipedia_field(item.name, 'title')

        logger.info('Title: %s' % item.wikipedia_title)

        # Description
        item.description = self.get_wikipedia_extract(item.wikipedia_title)

        logger.info('Description: %s' % item.description)

        # Image
        image_url = self.get_wikipedia_image(item.wikipedia_title)

        logger.info('Downloading image from: %s' % image_url)
        result = urllib.request.urlopen(image_url)
        item.image.delete(False)  # delete old image

        item.image.save(item.code + '.jpg', result)  # save new image

        return item

    def handle(self, *args, **options):
        items = Court.objects.order_by('-updated')[options['start']:]

        if options['limit'] > 0:
            items = items[:options['limit']]

        for item in items:
            if item.is_default():
                continue

            try:
                item = self.enrich_court(item)
            except ProcessingError as e:
                logger.error(e)

            # Always save
            item.save()


