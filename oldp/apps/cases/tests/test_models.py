import logging
import os
from datetime import date
from unittest import skip

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DataError
from django.test import TestCase, tag
from django.utils import timezone

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.processing.errors import ProcessingError
from oldp.utils.test_utils import mysql_only_test

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources")


@tag("models")
class CasesModelsTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        # CourtsTestCase.set_up_courts()
        pass

    def tearDown(self):
        # CourtsTestCase.tear_down_courts()
        pass

    def test_slug(self):
        Case.objects.create(
            pk=1, file_number="AB/123", slug="a-case-slug", court_id=Court.DEFAULT_ID
        )

        self.assertEqual(
            Case.objects.get(slug="a-case-slug").pk, 1, "Cannot get case by slug"
        )

    def test_field_validation_2(self):
        try:
            # max_length
            t = "A" * 201
            c = Case(title=t, file_number=t)
            c.full_clean()
            # c.save()

            raise ValueError("ValidationError should have been raised.")
        except ValidationError:
            pass

    @mysql_only_test
    def test_field_validation(self):
        try:
            # max_length
            t = "A" * 201
            c = Case(title=t, file_number=t)
            c.save()

            raise ValueError("DataError should have been raised.")
        except DataError:
            pass

    def from_json_directory(self, directory):
        """Test from_json_file method with different sources"""
        test_files = os.listdir(os.path.join(RESOURCE_DIR, directory))

        for f in test_files:
            f = os.path.join(RESOURCE_DIR, directory, f)
            self.from_json_file(f)

    def from_json_file(self, f):
        logger.debug("Test resource: %s" % f)

        case = Case.from_json_file(f)
        case.full_clean()
        case.save()

        self.assertGreaterEqual(
            len(case.text), 300, "Case text is too short: %s" % case.text
        )

        logger.debug("Test OK: %s" % case)

    @skip  # TODO fixtures need to fit to test files
    def test_from_json_file_bgh(self):
        self.from_json_directory("from_bgh")

    @skip  # TODO write with django serializer
    def test_section_json(self):
        self.from_json_file(
            os.path.join(
                RESOURCE_DIR, "from_bverfg/bverfg_incorrect_string_value_in_raw.json"
            )
        )

    # @skip  # TODO write with django serializer
    def test_raise_error_from_json_file(self):
        directory = os.path.join(RESOURCE_DIR, "invalid_cases")
        for f in os.listdir(directory):
            f = os.path.join(directory, f)

            logger.debug("Test resource: %s" % f)

            try:
                Case.from_json_file(f)
                raise ValueError("ProcessingError not raised with %s" % f)
            except ProcessingError:
                pass

    def test_case_serializable(self):
        # TODO >> With post processing FS
        file_path = os.path.join(settings.WORKING_DIR, "serialized_case.json")
        a = Case(file_number="ABC/123", date=date(year=2000, month=10, day=2))
        a.save()
        a_json = a.to_json(file_path)

        b = Case.from_json_file(file_path)
        b_json = b.to_json()

        # Clean up again
        os.remove(file_path)

        # Compare
        self.assertEqual(a_json, b_json)

    def test_get_content_as_html(self):
        """Test valid HTML output."""
        expected = "<h1>Some html</h1><p>foo</p>"
        obj = Case(content=expected, title="some title", file_number="ABC/123")
        obj.save()
        self.assertEqual(
            obj.get_content_as_html(), expected, "Invalid html conversation"
        )

    def test_get_short_title(self):
        title = "This is a very long title for an even more long cases to all extend"
        case = Case(title=title, file_number="ABC/123")

        self.assertEqual(13, len(case.get_short_title(10)), "Invalid title")

    def test_get_absolute_url(self):
        case = Case(title="Some titlr", file_number="ABC/123")

        self.assertTrue("no-slug" in case.get_absolute_url(), "Invalid url")

        case = Case(title="Some titlr", file_number="ABC/123", slug="abc")
        self.assertTrue("abc" in case.get_absolute_url(), "Invalid url")


@tag("models")
class CaseContentDriftTestCase(TestCase):
    """``Case.save()`` clears ``references_extracted_at`` when ``content``
    changes, so the next ``process_cases`` run heals the now-stale
    ``CaseReferenceMarker`` rows. See ``oldp.apps.cases.models.Case``.
    """

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def _make_case(self, content):
        case = Case.objects.create(
            slug="drift-test",
            file_number="DT/1",
            court_id=Court.DEFAULT_ID,
            content=content,
            references_extracted_at=timezone.now(),
        )
        # Round-trip through the DB so ``from_db`` populates the
        # snapshot of ``content`` and ``references_extracted_at``.
        return Case.objects.get(pk=case.pk)

    def test_changing_content_clears_extracted_at(self):
        case = self._make_case("<p>original</p>")
        self.assertIsNotNone(case.references_extracted_at)

        case.content = "<p>modified</p>"
        case.save()

        case.refresh_from_db()
        self.assertIsNone(case.references_extracted_at)

    def test_unchanged_content_preserves_extracted_at(self):
        case = self._make_case("<p>stable</p>")
        original_ts = case.references_extracted_at

        case.title = "new title"
        case.save()

        case.refresh_from_db()
        self.assertEqual(case.references_extracted_at, original_ts)

    def test_caller_refreshes_extracted_at_in_same_save(self):
        """Processing pipeline rewrites ``content`` and stamps
        ``references_extracted_at`` in the same save — that must not be
        clobbered by the drift guard.
        """
        case = self._make_case("<p>orig [ref=u]x[/ref]</p>")

        case.content = "<p>orig x</p>"
        new_ts = timezone.now()
        case.references_extracted_at = new_ts
        case.save()

        case.refresh_from_db()
        self.assertIsNotNone(case.references_extracted_at)

    def test_drift_guard_no_op_when_extracted_at_already_null(self):
        case = self._make_case("<p>stale</p>")
        case.references_extracted_at = None
        case.save()
        case.refresh_from_db()

        case.content = "<p>changed</p>"
        case.save()
        case.refresh_from_db()
        self.assertIsNone(case.references_extracted_at)
