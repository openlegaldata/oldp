"""Tests for profiling toggles (django-silk and django-querycount)."""

import unittest
from importlib.util import find_spec

from django.conf import settings
from django.test import TestCase, override_settings


class ProfilingSettingsTestCase(TestCase):
    """Test that profiling toggles are off by default and don't leak into normal config."""

    def test_profiling_disabled_by_default(self):
        """PROFILING_ENABLED defaults to False; silk not in INSTALLED_APPS or MIDDLEWARE."""
        self.assertFalse(settings.PROFILING_ENABLED)
        self.assertNotIn("silk", settings.INSTALLED_APPS)
        self.assertNotIn("silk.middleware.SilkyMiddleware", settings.MIDDLEWARE)

    def test_querycount_disabled_by_default(self):
        """QUERYCOUNT_ENABLED defaults to False; querycount not in MIDDLEWARE."""
        self.assertFalse(settings.QUERYCOUNT_ENABLED)
        self.assertNotIn(
            "querycount.middleware.QueryCountMiddleware", settings.MIDDLEWARE
        )

    def test_silk_url_not_registered_when_disabled(self):
        """When profiling is off, /silk/ returns 404."""
        response = self.client.get("/silk/")
        self.assertEqual(response.status_code, 404)


@unittest.skipUnless(find_spec("querycount"), "django-querycount not installed")
@override_settings(
    MIDDLEWARE=list(settings.MIDDLEWARE)
    + ["querycount.middleware.QueryCountMiddleware"],
    QUERYCOUNT={
        "THRESHOLDS": {
            "MEDIUM": 50,
            "HIGH": 200,
            "MIN_TIME_TO_LOG": 0,
            "MIN_QUERY_COUNT_TO_LOG": 0,
        },
        "DISPLAY_DUPLICATES": 5,
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class QuerycountMiddlewareTestCase(TestCase):
    """Test that querycount middleware works when enabled via settings override."""

    def test_querycount_middleware_runs_without_error(self):
        """The middleware integrates with Django and responds successfully."""
        response = self.client.get("/")
        self.assertIn(response.status_code, [200, 301, 302])
