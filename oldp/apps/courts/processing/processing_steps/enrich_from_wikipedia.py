import logging
import urllib

import requests

from oldp.apps.courts.models import Court
from oldp.apps.courts.processing import CourtProcessingStep
from oldp.apps.processing.errors import ProcessingError

logger = logging.getLogger(__name__)


class ProcessingStep(CourtProcessingStep):
    """
    Retrieves Wikipedia content to enrich court information
    """
    description = 'Enrich with Wikipedia content'
    language = 'de'

    def process(self, court: Court):
        if court.wikipedia_title is None:
            court.wikipedia_title = self.get_wikipedia_field(court.name, 'title')

        logger.info('Title: %s' % court.wikipedia_title)

        # Description
        court.description = self.get_wikipedia_extract(court.wikipedia_title)

        logger.info('Description: %s' % court.description)

        # Image
        image_url = self.get_wikipedia_image(court.wikipedia_title)

        logger.info('Downloading image from: %s' % image_url)
        result = urllib.request.urlopen(image_url)
        court.image.delete(False)  # delete old image

        court.image.save(court.code + '.jpg', result)  # save new image

        return court

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
