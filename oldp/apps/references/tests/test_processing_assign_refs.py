from django.test import TestCase, tag


@tag('processing')
class AssignReferencesTestCase(TestCase):
    """
    ./manage.py dumpdata references --output refs.json
    """
    fixtures = []

