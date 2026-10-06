"""Takedown / redaction record on cases (docs/content-moderation.md)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, tag
from django.urls import reverse

from oldp.apps.cases.exceptions import DuplicateCaseError
from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.set_review_accepted import (
    ProcessingStep as SetReviewAcceptedStep,
)
from oldp.apps.cases.serializers import CaseUpdateSerializer
from oldp.apps.cases.services.case_creator import CaseCreator
from oldp.apps.courts.models import Court

User = get_user_model()


@tag("cases", "moderation")
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class TakedownTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        self.case = Case.objects.create(
            court=self.court,
            file_number="MOD-001",
            date=date(2022, 5, 4),
            title="Mustermann ./. Stadt",
            abstract="Kläger Max Mustermann ...",
            content="<p>Der Kläger Max Mustermann, wohnhaft in ...</p>",
            raw="<html>Max Mustermann</html>",
            review_status="accepted",
        )

    def test_apply_takedown_hides_and_purges_but_keeps_key(self):
        self.case.apply_takedown(note="Report #1: party identifiable")
        self.case.save()
        self.case.refresh_from_db()

        self.assertEqual(self.case.review_status, "rejected")
        self.assertTrue(self.case.is_moderated)
        self.assertEqual(self.case.content, "")
        self.assertEqual(self.case.raw, "")
        self.assertEqual(self.case.abstract, "")
        self.assertIn("Report #1", self.case.moderation_note)
        # The dedupe key survives so the ingestor cannot re-create the case.
        self.assertEqual(self.case.file_number, "MOD-001")
        self.assertEqual(self.case.court, self.court)
        self.assertFalse(Case.get_queryset().filter(pk=self.case.pk).exists())

    def test_resubmission_after_takedown_is_a_duplicate(self):
        self.case.apply_takedown()
        self.case.save()
        creator = CaseCreator(extract_refs=False)
        self.assertTrue(creator.check_duplicate(self.court, "MOD-001"))
        with self.assertRaises(DuplicateCaseError):
            creator.create_case(
                court_name=self.court.name,
                file_number="MOD-001",
                date=date(2022, 5, 4),
                content="<p>Der Kläger Max Mustermann ...</p>",
            )

    def test_mark_redacted_keeps_case_online_and_blanks_raw(self):
        self.case.content = "<p>Der Kläger […], wohnhaft in ...</p>"
        self.case.mark_redacted(note="Report #2: name removed")
        self.case.save()
        self.case.refresh_from_db()
        self.assertEqual(self.case.review_status, "accepted")
        self.assertTrue(self.case.is_moderated)
        self.assertEqual(self.case.raw, "")
        self.assertIn("[…]", self.case.content)
        self.assertTrue(Case.get_queryset().filter(pk=self.case.pk).exists())

    def test_accept_step_refuses_moderated_case(self):
        self.case.apply_takedown()
        self.case.save()
        SetReviewAcceptedStep().process(self.case)
        self.assertEqual(self.case.review_status, "rejected")

        self.case.moderated_at = None
        SetReviewAcceptedStep().process(self.case)
        self.assertEqual(self.case.review_status, "accepted")

    def test_api_patch_cannot_reaccept_moderated_case(self):
        self.case.apply_takedown()
        self.case.save()
        serializer = CaseUpdateSerializer(
            instance=self.case, data={"review_status": "accepted"}, partial=True
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("review_status", serializer.errors)

        serializer = CaseUpdateSerializer(
            instance=self.case, data={"review_status": "pending"}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_admin_takedown_action(self):
        admin_user = User.objects.create_superuser("root", "root@example.com", "pw")
        self.client.force_login(admin_user)
        res = self.client.post(
            reverse("admin:cases_case_changelist"),
            {"action": "takedown_cases", "_selected_action": [self.case.pk]},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.review_status, "rejected")
        self.assertEqual(self.case.content, "")
        self.assertIn("root", self.case.moderation_note)

        res = self.client.post(
            reverse("admin:cases_case_changelist"),
            {"action": "clear_moderation", "_selected_action": [self.case.pk]},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)
        self.case.refresh_from_db()
        self.assertIsNone(self.case.moderated_at)
        self.assertEqual(self.case.review_status, "rejected")
        self.assertIn("Moderation cleared", self.case.moderation_note)
