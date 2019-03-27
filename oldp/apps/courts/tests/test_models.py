from django.test import TestCase, tag

from oldp.apps.courts.apps import CourtLocationLevel, CourtTypes
from oldp.apps.courts.models import Court, State, City, get_instance_or_create


@tag('models')
class CourtsModelsTestCase(TestCase):
    fixtures = [
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_get_court(self):
        self.assertEqual(Court.objects.get(pk=Court.DEFAULT_ID).get_id(), Court.DEFAULT_ID,
                         "Default court has not default id")

    def test_get_instance_or_create(self):
        c = get_instance_or_create(Court, name='Bundesverfassungsgericht')
        self.assertEqual(c.code, 'BVerfG')

    def test_get_by_slug(self):
        self.assertEqual(Court.objects.get(slug='ag-aalen').name, 'Amtsgericht Aalen', 'Invalid name')

    def test_pre_save(self):
        city = City(name='City', state_id=State.DEFAULT_ID)
        city.save()

        c = Court(city=city, court_type='AG', state_id=State.DEFAULT_ID)
        c.save()

        self.assertEqual(c.slug, 'ag-city', 'Slug not correctly generated in pre_save')

    def test_type_extraction(self):
        class TestCourtTypes(CourtTypes):
            def get_types(self):
                return {
                    'AG': {
                        'name': 'Amtsgericht',
                        'levels': [CourtLocationLevel.CITY]
                    },
                    'ARBG': {
                        'name': 'Arbeitsgericht',
                        'levels': [CourtLocationLevel.CITY]
                    },
                }

        with self.settings(COURT_TYPES=TestCourtTypes()):

            self.assertEqual(Court.extract_type_code_from_name('Amtsgericht Aalen'), 'AG')
            self.assertEqual(Court.extract_type_code_from_name('Arbeitsgericht Aalen'), 'ARBG')
        # ...

