from enum import Enum

from django.apps import AppConfig

from oldp.apps.processing.errors import ProcessingError


class CourtLocationLevel(Enum):
    CITY = 'city'
    STATE = 'state'
    COUNTRY = 'country'


class CourtsConfig(AppConfig):
    name = 'oldp.apps.courts'


class CourtTypes(object):
    def get_type(self, code):
        if code in self.get_types():
            return self.get_types()[code]
        else:
            raise ProcessingError('Code not defined: %s' % code)

    def get_types(self):
        raise NotImplementedError()

    def get_name_to_code_mapping(self):
        types = self.get_types()
        mapping = {}
        for k in types:
            mapping[types[k]['name']] = k

            if 'aliases' in types[k]:
                for alias in types[k]['aliases']:
                    mapping[alias] = k
        return mapping

    def get_all_to_code_mapping(self):
        mapping = self.get_name_to_code_mapping()

        for k in self.get_types():
            mapping[k] = k

        return mapping


class CourtTypesDefault(CourtTypes):
    def get_types(self):
        return {}


