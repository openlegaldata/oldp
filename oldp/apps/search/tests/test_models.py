import logging
import os

from django.test import TestCase
from elasticsearch_dsl import Search

from oldp.apps.cases.models import Case
from oldp.utils.elasticsearch import delete_elasticsearch_documents
from oldp.utils.test_utils import es_test

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


class SearchModelsTestCase(TestCase):
    """

    Do not forget to put DJANGO_TEST_WITH_ES to true

    """
    fixtures = [
        'search/courts.json',
        'search/cases.json'
    ]

    def setUp(self):
        delete_elasticsearch_documents(Case)

    def tearDown(self):
        # CourtsTestCase.tear_down_courts()
        pass

    # @es_test
    # def test_index(self):
    #     obj = Case.objects.get(pk=1)
    #
    #     self.assertTrue(obj.index(), 'Index operation did not return created=true')



