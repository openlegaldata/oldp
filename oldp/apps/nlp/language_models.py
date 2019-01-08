from abc import ABC, abstractmethod

import de_core_news_sm

from oldp.apps.nlp.models import Entity


class SpacyModel(ABC, object):

    @staticmethod
    @abstractmethod
    def load():
        pass

    @staticmethod
    @abstractmethod
    def get_entity_name(entity_type):
        pass


class GermanSpacyModel(SpacyModel):

    @staticmethod
    def load():
        # spacy.load() won't work with models over pip, use de_core_news_sm.load() instead.
        # see https://spacy.io/usage/models#models-loading
        return de_core_news_sm.load()

    @staticmethod
    def get_entity_name(entity_type):
        """The german model de_core_news_sm supports PER, LOC, ORG and MISC."""

        if entity_type == Entity.PERSON:
            return 'PER'
        elif entity_type == Entity.LOCATION:
            return 'LOC'
        elif entity_type == Entity.ORGANIZATION:
            return 'ORG'
        else:
            raise ValueError('Entity type {} not supported.'.format(entity_type))
