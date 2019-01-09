import re

from bs4 import BeautifulSoup

from oldp.apps.nlp.models import Entity, NLPContent
from oldp.apps.nlp.ner.base import EntityExtractor


def get_text_from_html(html):
    soup = BeautifulSoup(html, 'lxml')
    return re.sub(r'\s\s+', ' ', soup.get_text())


class EntityProcessor:  # TODO Can this be all done in ProcessingStep?
    SERIALIZATION_SEPERATOR = '^'
    entity_types = []

    def __init__(self):
        super(EntityProcessor, self).__init__()

    def clean_content(self, content):
        # HTML Tags
        pattern = re.compile(r'<[^>]+>')

        for m in re.finditer(pattern, content):
            mask = ' ' * (m.end(0) - m.start(0))
            content = content[:m.start(0)] + mask + content[m.end(0):]

        return content

    def extract_and_load(self,
                         text: str,
                         owner: NLPContent,
                         lang='de'):
        if len(self.entity_types) == 0:
            raise ValueError('No entity types given! Set them via public property entity_types.')

        # Remove existing entities
        owner.nlp_entities.all().delete()

        # Clean HTML
        text = self.clean_content(text)

        extractor = EntityExtractor(lang=lang)
        extractor.prepare(text)

        # Extract for each type
        for entity_type in self.entity_types:
            entities = extractor.extract(entity_type)
            for (value, start, end) in entities:

                # Prepare value
                value = str(value).strip()

                # Only add non-empty entities
                if value != '':
                    entity = Entity(type=entity_type,
                                    value=value,
                                    pos_start=start,
                                    pos_end=end)
                    entity.save()
                    owner.nlp_entities.add(entity)
