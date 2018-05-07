from enum import Enum

from django.apps import AppConfig

CourtLocationLevel = Enum('CourtLocationLevel', 'CITY STATE COUNTRY')


class CourtsConfig(AppConfig):
    name = 'oldp.apps.courts'


class CourtTypes(object):
    def get_type(self, code):
        return self.get_types()[code]

    @staticmethod
    def get_types():
        return {
            'AG': {
                'name': 'Amtsgericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'ARBG': {
                'name': 'Arbeitsgericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'BAG': {
                'name': 'Bundesarbeitsgericht',
                'levels': []
            },
            'BGH': {
                'name': 'Bundesgerichtshof',
                'levels': []
            },
            'BFH': {
                'name': 'Bundesfinanzhof',
                'levels': []
            },
            'BSG': {
                'name': 'Bundessozialgericht',
                'levels': []
            },
            'BVerfG': {
                'name': 'Bundesverfassungsgericht',
                'levels': []
            },
            'BVerwG': {
                'name': 'Bundesverwaltungsgericht',
                'levels': []
            },
            # 'BGH': {
            #     'name': 'Berufsgericht für Heilberufe',
            #     'levels': [CourtLocationLevel.CITY]
            # },
            # 'DG': {
            #     'name': 'Dienstgericht für Richter'
            # }
            'FG': {
                'name': 'Finanzgericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'LAG': {
                'name': 'Landesarbeitsgericht',
                'levels': [CourtLocationLevel.STATE]
            },
            'LSG': {
                'name': 'Landessozialgericht',
                'levels': [CourtLocationLevel.STATE]
            },
            'LVG': {
                'name': 'Landesverfassungsgericht',
                'levels': [CourtLocationLevel.STATE]
            },
            'LBGH': {
                'name': 'Landesberufsgericht',
                'levels': [CourtLocationLevel.STATE]
            },
            'LG': {
                'name': 'Landgericht',
                'levels': [CourtLocationLevel.CITY, CourtLocationLevel.STATE]
            },
            'OLG': {
                'name': 'Oberlandesgericht',
                'levels': [CourtLocationLevel.STATE]
            },
            'OBLG': {
                'name': 'Oberstes Landesgericht',
                'levels': [CourtLocationLevel.STATE]
            },
            'OVG': {
                'name': 'Oberverwaltungsgericht',
                'levels': [CourtLocationLevel.STATE]
            },
            'SG': {
                'name': 'Sozialgericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'STGH': {
                'name': 'Staatsgerichtshof',
                'levels': [CourtLocationLevel.STATE]
            },
            'SCHG': {
                'name': 'Schifffahrtsgericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'SCHOG': {
                'name': 'Schifffahrtsobergericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'VERFG': {
                'name': 'Verfassungsgerichtshof',
                'aliases': ['Verfassungsgericht'],
                'levels': [CourtLocationLevel.STATE]
            },
            'VG': {
                'name': 'Verwaltungsgericht',
                'levels': [CourtLocationLevel.CITY, CourtLocationLevel.STATE]
            },
            'VGH': {
                'name': 'Verwaltungsgerichtshof',
                'levels': [CourtLocationLevel.STATE]
            },
            'KG': {
                'name': 'Kammergericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'EuGH': {
                'name': 'Europäischer Gerichtshof',
                'levels': []
            },
            'AWG': {
                'name': 'Anwaltsgericht',
                'aliases': ['Anwaltsgerichtshof'],
                'levels': [CourtLocationLevel.STATE],
            },
            'MSCHOG': {
                'name': 'Moselschifffahrtsobergericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'RSCHGD': {
                'name': 'Rheinschifffahrtsgericht',
                'levels': [CourtLocationLevel.CITY]
            },
            'RSCHOG': {
                'name': 'Rheinschifffahrtsobergericht',
                'levels': [CourtLocationLevel.CITY]
            }
            # TODO add more
        }

    @staticmethod
    def get_name_to_code_mapping():
        types = CourtTypes.get_types()
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
