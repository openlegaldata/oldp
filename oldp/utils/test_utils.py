import logging
import os
from unittest import TestCase

from django.conf import settings

logger = logging.getLogger(__name__)


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
        with open(self.get_resource(file_name), 'r') as f:
            return f.read()

    def assert_items_equal(self, expected, actual, msg, debug=False):
        if debug:
            logger.debug('Expected:\t%s\nActual:\t%s' % (sorted(expected), sorted(actual)))

        TestCase().assertTrue(len(expected) == len(actual) and sorted(expected) == sorted(actual), msg)

    # @staticmethod
    # def get_log_level():
    #     return get_log_level_from_env('OLDP_TEST_LOG_LEVEL', 'debug')


def mysql_only_test(fn):
    """Use this decorator for tests (e.g. DataErrors, IntegrityErrors) that apply only with MySQL (not SQLite)"""
    def modified_fn(x):
        if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.mysql':
            logger.warning('Skip test (DB is not MySQL): %s' % fn.__name__)
        else:
            return fn(x)

    return modified_fn


def web_test(fn):
    """Use this decorator for tests that interact with external websites"""
    def modified_fn(x):
        if not settings.TEST_WITH_WEB:
            logger.warning('Skip test (without web): %s' % fn.__name__)
        else:
            return fn(x)

    return modified_fn


def es_test(fn):
    """Use this decorator for tests that require Elasticsearch"""
    def modified_fn(x):
        if not settings.TEST_WITH_ES:
            logger.warning('Skip test (without Elasticsearch): %s' % fn.__name__)
        else:
            return fn(x)

    return modified_fn


def selenium_test(fn):
    """Use this decorator for tests that require Selenium/Webdriver"""
    def modified_fn(x):
        if not settings.TEST_WITH_SELENIUM:
            logger.warning('Skip test (without Selenium/Webdriver): %s' % fn.__name__)
        else:
            return fn(x)

    return modified_fn
