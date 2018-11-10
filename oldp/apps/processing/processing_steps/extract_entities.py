from bs4 import BeautifulSoup
import re

from oldp.apps.nlp.models import Entity
from oldp.apps.nlp.ner import EntityExtractor


def get_text_from_html(html):
    soup = BeautifulSoup(html, 'lxml')
    return re.sub(r'\s\s+', ' ', soup.get_text())


class EntityProcessor:

    def __init__(self):
        super(EntityProcessor, self).__init__()
        self.entity_types = []

    def extract_and_load(self, text, nlp_content, lang='de'):
        if len(self.entity_types) == 0:
            raise ValueError('No entity types given! Set them via public property entity_types.')
        extractor = EntityExtractor(lang=lang)
        extractor.prepare(text)
        for entity_type in self.entity_types:
            entities = extractor.extract(entity_type)
            for (value, start, end) in entities:
                entity = Entity(nlp_content=nlp_content,
                                type=entity_type,
                                value=value,
                                pos_start=start,
                                pos_end=end)
                entity.save()
