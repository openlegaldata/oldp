from django.core.management import call_command
from django.test import TestCase, tag

from oldp.utils.test_utils import ElasticsearchTestMixin, es_test


@tag("commands")
class SearchCommandsTestCase(ElasticsearchTestMixin, TestCase):
    """Test search commands with Elasticsearch (uses mock backend by default)."""

    fixtures = [
        "laws/laws.json",
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def setUp(self):
        super().setUp()
        # Index fixture data into mock backend
        self.index_fixtures()

    def tearDown(self):
        pass

    @es_test
    def test_generate_related_law(self):
        call_command("generate_related", *["law"], **{"limit": 10})

    @es_test
    def test_generate_related_case(self):
        call_command("generate_related", *["case"], **{"limit": 10})
