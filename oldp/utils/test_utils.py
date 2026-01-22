import logging
import os
from functools import wraps
from unittest import TestCase

from django.conf import settings

logger = logging.getLogger(__name__)


def _is_mock_es_enabled():
    """Check if mock ES is enabled in settings."""
    return getattr(settings, "MOCK_ES_TESTS", False)


def _reset_mock_backend():
    """Reset the mock backend if it's being used."""
    if _is_mock_es_enabled():
        from oldp.apps.search.mock_backend import MockElasticsearchBackend

        MockElasticsearchBackend.reset()


class TestCaseHelper(object):
    resource_dir = None

    @staticmethod
    def get_app_root_dir():
        return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

    def get_resource_dir(self):
        # return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')
        return self.resource_dir

    def get_resource(self, file_name):
        return os.path.join(self.get_resource_dir(), file_name)

    def get_resource_as_string(self, file_name):
        with open(self.get_resource(file_name), "r") as f:
            return f.read()

    def assert_items_equal(self, expected, actual, msg, debug=False):
        if debug:
            logger.debug(
                "Expected:\t%s\nActual:\t%s" % (sorted(expected), sorted(actual))
            )

        TestCase().assertTrue(
            len(expected) == len(actual) and sorted(expected) == sorted(actual), msg
        )

    # @staticmethod
    # def get_log_level():
    #     return get_log_level_from_env('OLDP_TEST_LOG_LEVEL', 'debug')


class ElasticsearchTestMixin:
    """Mixin for test cases that use Elasticsearch.

    Provides setUp() method that resets the mock backend and an index_fixtures()
    helper to index test data into the mock backend.

    Usage:
        class SearchViewsTestCase(ElasticsearchTestMixin, LiveServerTestCase):
            fixtures = ["courts/courts.json", "cases/cases.json"]

            def setUp(self):
                super().setUp()
                self.index_fixtures()  # Index fixture data into mock backend
    """

    def setUp(self):
        """Reset mock backend before each test."""
        super().setUp()
        _reset_mock_backend()

    def index_fixtures(self, models=None):
        """Index fixture data into the search backend (mock or real).

        This method indexes all objects from the specified models (or all indexed
        models if not specified) into the search backend.

        Args:
            models: Optional list of model classes to index. If None, indexes all
                    models that have SearchIndex classes registered.
        """
        from haystack import connections

        backend = connections["default"].get_backend()
        unified_index = connections["default"].get_unified_index()

        if models is None:
            # Get all indexed models
            models = unified_index.get_indexed_models()

        for model in models:
            index = unified_index.get_index(model)
            if index:
                # Get all objects for this model
                queryset = index.index_queryset()
                if queryset.exists():
                    backend.update(index, queryset)
                    logger.debug(
                        "ElasticsearchTestMixin: Indexed %d %s objects",
                        queryset.count(),
                        model.__name__,
                    )


def mysql_only_test(fn):
    """Use this decorator for tests (e.g. DataErrors, IntegrityErrors) that apply only with MySQL (not SQLite)"""

    @wraps(fn)
    def modified_fn(x):
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.mysql":
            logger.warning("Skip test (DB is not MySQL): %s" % fn.__name__)
            x.skipTest("DB is not MySQL")
        return fn(x)

    return modified_fn


def web_test(fn):
    """Use this decorator for tests that interact with external websites"""

    @wraps(fn)
    def modified_fn(x):
        if not settings.TEST_WITH_WEB:
            logger.warning("Skip test (without web): %s" % fn.__name__)
            x.skipTest("TEST_WITH_WEB is False")
        return fn(x)

    return modified_fn


def es_test(fn):
    """Use this decorator for tests that require Elasticsearch.

    When MOCK_ES_TESTS=True (default), tests run with the mock backend.
    When TEST_WITH_ES=False, tests are skipped.
    """

    @wraps(fn)
    def modified_fn(x):
        if not settings.TEST_WITH_ES:
            logger.warning("Skip test (without Elasticsearch): %s" % fn.__name__)
            x.skipTest("TEST_WITH_ES is False")
        # Reset mock backend before each test when using mocks
        _reset_mock_backend()
        return fn(x)

    return modified_fn


def real_es_test(fn):
    """Use this decorator for tests that require real Elasticsearch.

    These tests will be skipped when MOCK_ES_TESTS=True.
    """

    @wraps(fn)
    def modified_fn(x):
        if not settings.TEST_WITH_ES:
            logger.warning("Skip test (without Elasticsearch): %s" % fn.__name__)
            x.skipTest("TEST_WITH_ES is False")
        if _is_mock_es_enabled():
            logger.warning("Skip test (requires real Elasticsearch): %s" % fn.__name__)
            x.skipTest("MOCK_ES_TESTS is True - test requires real Elasticsearch")
        return fn(x)

    return modified_fn


def selenium_test(fn):
    """Use this decorator for tests that require Selenium/Webdriver"""

    @wraps(fn)
    def modified_fn(x):
        if not settings.TEST_WITH_SELENIUM:
            logger.warning("Skip test (without Selenium/Webdriver): %s" % fn.__name__)
            x.skipTest("TEST_WITH_SELENIUM is False")
        return fn(x)

    return modified_fn
