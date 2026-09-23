"""A user must not annotate with another user's label.

``Annotation.get_owner()`` returns ``self.label.owner``, so the label chosen on
create decides who the annotation belongs to. The viewsets had no
``perform_create`` and the serializer accepted any ``AnnotationLabel`` pk, so an
authenticated user could post against a victim's private label and have the row
attributed to the victim -- visible to them and to staff as their own entry,
consuming their per-label constraints.

``OwnerPrivatePermission`` did not stop it: DRF only calls
``has_object_permission`` for an existing object, so on create the sole gate was
``is_authenticated``.
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.annotations.models import AnnotationLabel, CaseAnnotation
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class AnnotationLabelIdorTestCase(APITestCase):
    def setUp(self):
        self.attacker = User.objects.create_user("zq_attacker", "a@x.invalid", "pw")
        self.victim = User.objects.create_user("zq_victim", "v@x.invalid", "pw")
        self.staff = User.objects.create_user(
            "zq_staff", "s@x.invalid", "pw", is_staff=True
        )

        country, _ = Country.objects.get_or_create(
            code="DE", defaults={"name": "Germany"}
        )
        state, _ = State.objects.get_or_create(
            pk=1, defaults={"name": "T", "country": country, "slug": "t"}
        )
        court = Court.objects.create(
            name="ZQ IDOR Court", slug="zq-idor", code="ZQIDOR", state=state
        )
        self.case = Case.objects.create(
            court=court,
            slug="zq-idor-case",
            file_number="ZQ 1/24",
            content="<p>body</p>",
            review_status="accepted",
        )

        self.victim_private = AnnotationLabel.objects.create(
            name="Victim private",
            slug="victim-private",
            owner=self.victim,
            private=True,
        )
        self.victim_public = AnnotationLabel.objects.create(
            name="Victim public", slug="victim-public", owner=self.victim, private=False
        )
        self.attacker_label = AnnotationLabel.objects.create(
            name="Attacker own", slug="attacker-own", owner=self.attacker, private=True
        )

    def _post(self, user, label, path="/api/case_annotations/"):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.post(
            path,
            {"belongs_to": self.case.id, "label": label.id, "value_str": "injected"},
        )

    # --- the reported attack ---

    def test_cannot_annotate_with_another_users_private_label(self):
        res = self._post(self.attacker, self.victim_private)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CaseAnnotation.objects.count(), 0)

    def test_cannot_annotate_with_another_users_public_label(self):
        """Public is not a loophole: ownership still transfers to the label owner."""
        res = self._post(self.attacker, self.victim_public)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CaseAnnotation.objects.count(), 0)

    def _post_marker(self, user, label):
        client = APIClient()
        client.force_authenticate(user=user)
        # ``value_str`` is required; without it the request is rejected for that
        # instead, which would make this test pass for the wrong reason.
        return client.post(
            "/api/case_markers/",
            {
                "belongs_to": self.case.id,
                "label": label.id,
                "value_str": "injected",
                "start": 0,
                "end": 4,
            },
        )

    def test_marker_endpoint_is_guarded_too(self):
        res = self._post_marker(self.attacker, self.victim_private)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("label", res.json())

    def test_marker_with_own_label_succeeds(self):
        """Pins that the marker rejection above is the guard, not a bad payload."""
        res = self._post_marker(self.attacker, self.attacker_label)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    # --- legitimate use must still work ---

    def test_user_can_annotate_with_own_label(self):
        res = self._post(self.attacker, self.attacker_label)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CaseAnnotation.objects.get().get_owner(), self.attacker)

    def test_staff_retain_existing_reach(self):
        """Staff already see every annotation; this fix must not narrow that."""
        res = self._post(self.staff, self.victim_private)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_anonymous_cannot_create(self):
        client = APIClient()
        res = client.post(
            "/api/case_annotations/",
            {"belongs_to": self.case.id, "label": self.victim_private.id},
        )
        self.assertIn(
            res.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertEqual(CaseAnnotation.objects.count(), 0)
