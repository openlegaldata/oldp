import logging
from io import BytesIO

import requests

from oldp.apps.courts.models import Court
from oldp.apps.courts.processing import CourtProcessingStep
from oldp.apps.processing.errors import ProcessingError
from oldp.utils.version import get_version

logger = logging.getLogger(__name__)


class ProcessingStep(CourtProcessingStep):
    """Retrieves Wikipedia content to enrich court information"""

    description = "Enrich with Wikipedia content"
    language = "de"

    def process(self, court: Court):
        if court.wikipedia_title is None:
            court.wikipedia_title = self.get_wikipedia_field(court.name, "title")

        logger.info("Title: %s" % court.wikipedia_title)

        # Description
        court.description = self.get_wikipedia_extract(court.wikipedia_title)

        logger.info("Description: %s" % court.description)

        # Image
        image_url = self.get_wikipedia_image(court.wikipedia_title)

        logger.info("Downloading image from: %s" % image_url)
        res = self.get_request(image_url)

        if res.status_code == 200:
            court.image.delete(False)  # delete old image

            # Wrap bytes content in BytesIO for Django ImageField
            image_file = BytesIO(res.content)
            court.image.save(court.code + ".jpg", image_file)  # save new image

            return court

        raise ProcessingError(
            f"Cannot download image file from Wikipedia API: {res.status_code} from {res.text}"
        )

    @staticmethod
    def get_request(url):
        """Perform HTTP GET request with user agent header."""
        return requests.get(
            url,
            headers={
                "User-agent": f"oldp/{get_version()} (https://github.com/openlegaldata/oldp/)",
            },
        )

    def get_wikipedia_field(self, query, field="pageid"):
        # Get Wikipedia ID from search API
        res = self.get_request(
            "https://"
            + self.language
            + ".wikipedia.org/w/api.php?action=query&list=search&srsearch=%s&utf8=&format=json"
            % query
        )

        if res.status_code == 200:
            res_obj = res.json()
            if len(res_obj["query"]["search"]) > 0:
                return res_obj["query"]["search"][0][field]

        raise ProcessingError(
            f"Cannot get field from Wikipedia search API: {res.status_code} from {res.text}"
        )

    def get_wikipedia_image(self, query, size=250):
        res = self.get_request(
            "https://"
            + self.language
            + ".wikipedia.org/w/api.php?action=query&titles=%s&prop=pageimages&format=json&pithumbsize=%i"
            % (query, size)
        )

        if res.status_code == 200:
            res_obj = res.json()
            # print(res_obj['query']['pages'])
            for p in res_obj["query"]["pages"]:
                if "thumbnail" in res_obj["query"]["pages"][p]:
                    return res_obj["query"]["pages"][p]["thumbnail"]["source"]

        raise ProcessingError(
            f"Cannot get image URL from Wikipedia API: {res.status_code} from {res.text}"
        )

    def get_wikipedia_extract(self, query):
        res = self.get_request(
            "https://"
            + self.language
            + ".wikipedia.org/w/api.php?format=json&action=query&prop=extracts&exintro=&explaintext=&titles=%s"
            % query
        )

        if res.status_code == 200:
            res_obj = res.json()
            for p in res_obj["query"]["pages"]:
                return res_obj["query"]["pages"][p]["extract"]

        raise ProcessingError(
            f"Cannot get page extract from Wikipedia API: {res.status_code} from {res.text}"
        )
