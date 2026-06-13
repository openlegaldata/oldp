"""Regression tests for drf_yasg (Swagger) schema generation of the stats API.

``CaseStatsViewSet`` is a ``GenericViewSet`` without a ``serializer_class`` (it
builds plain dicts in ``list``/the ``@action`` methods). During schema
generation drf_yasg introspects the view and calls ``get_serializer()``, which
trips DRF's ``assert self.serializer_class is not None``. drf_yasg catches the
exception but logs a warning via ``drf_yasg.inspectors.base`` and emits an
empty/incorrect schema for every ``/api/cases/stats/*`` endpoint.

These tests drive the schema generator the same way the ``/api/swagger.json``
endpoint does and assert that no such exception is raised/logged.
"""

import logging

from django.test import RequestFactory, TestCase


class _RaiseOnRecordHandler(logging.Handler):
    """Logging handler that records emitted log records for assertions."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class CaseStatsSchemaGenerationTestCase(TestCase):
    """Schema generation for the stats viewset must not raise or warn."""

    def test_get_serializer_does_not_raise_in_fake_view(self):
        """A swagger_fake_view must yield a serializer instead of asserting.

        This is the exact call drf_yasg makes during introspection. Before the
        fix it raised ``AssertionError`` because ``serializer_class is None``.
        """
        from oldp.apps.cases.stats_api_views import CaseStatsViewSet

        view = CaseStatsViewSet()
        view.swagger_fake_view = True
        view.request = RequestFactory().get("/api/cases/stats/")
        view.format_kwarg = None

        # Must not raise.
        serializer = view.get_serializer()
        self.assertIsNotNone(serializer)

    def test_schema_generation_logs_no_inspector_exception(self):
        """Generating the full schema must not log a drf_yasg inspector error.

        The warning drf_yasg emits when ``get_serializer`` raises is logged at
        WARNING level on the ``drf_yasg.inspectors.base`` logger. Capture that
        logger and assert it stays silent while the stats endpoints are
        introspected.
        """
        from drf_yasg import openapi
        from drf_yasg.generators import OpenAPISchemaGenerator
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        handler = _RaiseOnRecordHandler()
        inspector_logger = logging.getLogger("drf_yasg.inspectors.base")
        previous_level = inspector_logger.level
        inspector_logger.addHandler(handler)
        inspector_logger.setLevel(logging.WARNING)
        try:
            generator = OpenAPISchemaGenerator(
                info=openapi.Info(title="Test API", default_version="v1"),
                version="v1",
                url="http://testserver/api/",
            )
            # drf_yasg clones the request per view, which requires a
            # DRF-wrapped request (not a bare WSGIRequest).
            request = Request(APIRequestFactory().get("/api/swagger.json"))
            schema = generator.get_schema(request=request, public=True)
        finally:
            inspector_logger.removeHandler(handler)
            inspector_logger.setLevel(previous_level)

        offending = [
            r.getMessage()
            for r in handler.records
            if "CaseStatsViewSet" in r.getMessage() or "stats" in r.getMessage().lower()
        ]
        self.assertEqual(
            offending,
            [],
            msg=(
                "drf_yasg logged a schema-generation warning for the stats "
                f"viewset: {offending}"
            ),
        )

        # The stats endpoints should be present in the generated schema with a
        # real (non-empty) 200 response schema rather than the empty schema the
        # bug produced.
        paths = schema["paths"]
        self.assertIn("/api/cases/stats/", paths)
        response_schema = paths["/api/cases/stats/"]["get"]["responses"]["200"][
            "schema"
        ]
        self.assertTrue(
            response_schema.get("properties"),
            msg=f"stats endpoint has an empty response schema: {response_schema}",
        )
