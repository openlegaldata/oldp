from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from oldp.apps.accounts.models import APIToken

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _rest_framework_settings(user_rate):
    """Return a REST_FRAMEWORK dict with a custom user throttle rate."""
    return {
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
        ],
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
        "DEFAULT_FILTER_BACKENDS": (
            "django_filters.rest_framework.DjangoFilterBackend",
        ),
        "PAGE_SIZE": 50,
        "DEFAULT_RENDERER_CLASSES": (
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
            "rest_framework_xml.renderers.XMLRenderer",
        ),
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "oldp.apps.accounts.authentication.CombinedTokenAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ),
        "DEFAULT_THROTTLE_CLASSES": (
            "rest_framework.throttling.AnonRateThrottle",
            "oldp.api.throttling.TokenUserRateThrottle",
        ),
        "DEFAULT_THROTTLE_RATES": {
            "anon": "100/day",
            "user": user_rate,
        },
        "EXCEPTION_HANDLER": "oldp.api.exceptions.full_details_exception_handler",
    }


# A public endpoint that doesn't require model permissions
API_ENDPOINT = "/api/"


@override_settings(
    CACHES=LOCMEM_CACHE,
    REST_FRAMEWORK=_rest_framework_settings("3/hour"),
)
class ThrottlingTestCase(TestCase):
    """Tests for TokenUserRateThrottle."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="throttle_user", password="testpass123"
        )
        self.token = APIToken.objects.create(user=self.user, name="Test Token")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def tearDown(self):
        cache.clear()

    def test_authenticated_user_is_throttled(self):
        """Authenticated requests exceeding the rate limit get 429."""
        for i in range(3):
            response = self.client.get(API_ENDPOINT)
            self.assertEqual(
                response.status_code, 200, f"Request {i + 1} should succeed"
            )

        response = self.client.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 429)

    def test_anonymous_not_affected_by_user_throttle(self):
        """Anonymous requests are not counted by the user throttle."""
        anon_client = APIClient()
        # The anon rate is 100/day, so 4 requests should be fine
        for i in range(4):
            response = anon_client.get(API_ENDPOINT)
            self.assertEqual(
                response.status_code, 200, f"Anon request {i + 1} should succeed"
            )

    def test_token_custom_rate_overrides_default(self):
        """A token with rate_limit=5 allows 5 requests when default is 3."""
        self.token.rate_limit = 5
        self.token.save()

        for i in range(5):
            response = self.client.get(API_ENDPOINT)
            self.assertEqual(
                response.status_code, 200, f"Request {i + 1} should succeed"
            )

        response = self.client.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 429)

    def test_token_lower_custom_rate(self):
        """A token with rate_limit=2 blocks at 2 when default is 3."""
        self.token.rate_limit = 2
        self.token.save()

        for i in range(2):
            response = self.client.get(API_ENDPOINT)
            self.assertEqual(
                response.status_code, 200, f"Request {i + 1} should succeed"
            )

        response = self.client.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 429)

    def test_session_auth_uses_default_rate(self):
        """Session-authenticated users get the default rate (no APIToken)."""
        session_client = APIClient()
        session_client.login(username="throttle_user", password="testpass123")

        for i in range(3):
            response = session_client.get(API_ENDPOINT)
            self.assertEqual(
                response.status_code, 200, f"Request {i + 1} should succeed"
            )

        response = session_client.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 429)

    def test_429_has_retry_after_header(self):
        """Throttled response includes Retry-After header."""
        for _ in range(3):
            self.client.get(API_ENDPOINT)

        response = self.client.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_separate_counters_per_user(self):
        """User A hitting the limit does not affect user B."""
        # Exhaust user A's quota
        for _ in range(3):
            self.client.get(API_ENDPOINT)
        response = self.client.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 429)

        # User B should still be able to make requests
        user_b = User.objects.create_user(
            username="throttle_user_b", password="testpass123"
        )
        token_b = APIToken.objects.create(user=user_b, name="Token B")
        client_b = APIClient()
        client_b.credentials(HTTP_AUTHORIZATION=f"Token {token_b.key}")

        response = client_b.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 200)

    def test_rate_limit_zero_blocks_all(self):
        """A token with rate_limit=0 blocks immediately."""
        self.token.rate_limit = 0
        self.token.save()

        response = self.client.get(API_ENDPOINT)
        self.assertEqual(response.status_code, 429)
