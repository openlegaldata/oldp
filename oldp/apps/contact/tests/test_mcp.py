"""Tests for the ``submit_feedback`` MCP tool (oldp.apps.contact.mcp)."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from oauth2_provider.models import AccessToken, get_application_model
from rest_framework.test import APIClient

from oldp.apps.contact.mcp import FeedbackTools

User = get_user_model()
Application = get_application_model()

_MESSAGE = "The search for Eigenbedarf misses recent BGH decisions from 2025."

_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mcp-feedback-tests",
    }
}


@override_settings(
    CACHES=_LOCMEM,
    SITE_EMAIL="team@example.org",
    DEFAULT_FROM_EMAIL="no-reply@example.org",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class SubmitFeedbackToolTests(TestCase):
    """Unit tests calling the toolset method directly."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="agentuser", email="agent@example.org", password="pw"
        )

    def _tools(self, user=None, auth=None):
        request = SimpleNamespace(user=user or self.user, auth=auth)
        return FeedbackTools(request=request)

    def test_anonymous_is_rejected(self):
        result = self._tools(user=AnonymousUser()).submit_feedback(
            category="bug_report", message=_MESSAGE
        )
        self.assertIn("error", result)
        self.assertIn("signed-in", result["error"])
        self.assertIn("signup_url", result)
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_email_like_contact_form(self):
        result = self._tools().submit_feedback(
            category="feature_request",
            message=_MESSAGE,
            subject="Better\nrecall",
            context="search_cases(query='Eigenbedarf')",
        )
        self.assertTrue(result["submitted"])
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["team@example.org"])
        self.assertEqual(sent.from_email, "no-reply@example.org")
        self.assertEqual(sent.reply_to, ["agent@example.org"])
        self.assertEqual(sent.subject, "MCP feedback (Feature request): Better recall")
        self.assertIn("User: agentuser", sent.body)
        self.assertIn("search_cases(query='Eigenbedarf')", sent.body)
        self.assertIn(_MESSAGE, sent.body)

    def test_subject_defaults_to_first_line_of_message(self):
        first_line = "word " * 30  # 150 characters
        self._tools().submit_feedback(
            category="bug_report", message=f"{first_line}\nDetails follow here."
        )
        self.assertEqual(
            mail.outbox[0].subject,
            "MCP feedback (Bug report): " + " ".join(first_line.split())[:80] + "…",
        )

    def test_short_first_line_is_not_truncated(self):
        self._tools().submit_feedback(category="bug_report", message=_MESSAGE)
        self.assertEqual(
            mail.outbox[0].subject, "MCP feedback (Bug report): " + _MESSAGE
        )

    def test_oauth_client_name_in_body(self):
        auth = SimpleNamespace(application=SimpleNamespace(name="Claude"))
        self._tools(auth=auth).submit_feedback(category="other", message=_MESSAGE)
        self.assertIn("Client: Claude", mail.outbox[0].body)
        self.assertIn("Auth: oauth", mail.outbox[0].body)

    def test_no_reply_to_without_user_email(self):
        user = User.objects.create_user(username="noemail", password="pw")
        self._tools(user=user).submit_feedback(category="other", message=_MESSAGE)
        self.assertEqual(mail.outbox[0].reply_to, [])

    def test_invalid_input(self):
        tools = self._tools()
        cases = [
            {"category": "praise", "message": _MESSAGE},
            {"category": "bug_report", "message": "too short"},
            {"category": "bug_report", "message": "x " * 3000},
            {"category": "bug_report", "message": _MESSAGE, "subject": "s" * 201},
            {"category": "bug_report", "message": _MESSAGE, "context": "c" * 2001},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=list(kwargs)):
                self.assertIn("error", tools.submit_feedback(**kwargs))
        self.assertEqual(len(mail.outbox), 0)

    def test_category_is_case_insensitive(self):
        result = self._tools().submit_feedback(
            category=" Bug_Report ", message=_MESSAGE
        )
        self.assertEqual(result["category"], "bug_report")

    @override_settings(MCP_FEEDBACK_DAILY_LIMIT=2)
    def test_daily_limit_per_user(self):
        tools = self._tools()
        for _ in range(2):
            self.assertTrue(
                tools.submit_feedback(category="other", message=_MESSAGE)["submitted"]
            )
        result = tools.submit_feedback(category="other", message=_MESSAGE)
        self.assertIn("limit", result["error"])
        self.assertEqual(len(mail.outbox), 2)

        other = User.objects.create_user(username="other", password="pw")
        result = self._tools(user=other).submit_feedback(
            category="other", message=_MESSAGE
        )
        self.assertTrue(result["submitted"])

    @override_settings(MCP_FEEDBACK_DAILY_LIMIT=1)
    def test_send_failure_is_retryable_and_not_counted(self):
        tools = self._tools()
        with mock.patch(
            "oldp.apps.contact.mcp.EmailMessage.send", side_effect=OSError("smtp down")
        ):
            result = tools.submit_feedback(category="other", message=_MESSAGE)
        self.assertTrue(result["retryable"])
        # The failed attempt does not use up the daily budget.
        self.assertTrue(
            tools.submit_feedback(category="other", message=_MESSAGE)["submitted"]
        )


@override_settings(
    CACHES=_LOCMEM,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class SubmitFeedbackEndpointTests(TestCase):
    """End-to-end through /mcp, checking the auth wiring."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _post(self, payload, **extra):
        return self.client.post(
            "/mcp",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            **extra,
        )

    @staticmethod
    def _payload(name="submit_feedback", request_id=1):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": {"category": "bug_report", "message": _MESSAGE},
            },
        }

    def _call(self, **extra):
        response = self._post(self._payload(), **extra)
        self.assertEqual(response.status_code, 200)
        content = response.json()["result"]["content"][0]["text"]
        return json.loads(content)

    def test_anonymous_call_gets_401_with_oauth_challenge(self):
        """A 401 with ``resource_metadata`` makes MCP clients offer sign-in.

        With a 200 + error text, a connector set to sign in only "when the
        server asks" never shows its Connect prompt.
        """
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 401)
        challenge = response["WWW-Authenticate"]
        self.assertTrue(challenge.startswith("Bearer "))
        self.assertIn(
            'resource_metadata="http://testserver/.well-known/'
            'oauth-protected-resource/mcp"',
            challenge,
        )
        self.assertIn("submit_feedback", response.content.decode())
        self.assertEqual(len(mail.outbox), 0)

    def test_anonymous_batch_with_feedback_call_gets_401(self):
        response = self._post(
            [self._payload("whoami", 1), self._payload("submit_feedback", 2)]
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(mail.outbox), 0)

    def test_anonymous_call_of_open_tool_still_answers(self):
        response = self._post(self._payload("whoami"))
        self.assertEqual(response.status_code, 200)

    def test_oauth_call_sends_email(self):
        user = User.objects.create_user(
            username="oauthagent", email="o@example.org", password="pw"
        )
        app = Application.objects.create(
            name="Test connector",
            user=user,
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://example.com/callback",
        )
        token = AccessToken.objects.create(
            user=user,
            application=app,
            token="feedback-oauth-token",
            expires=timezone.now() + timedelta(hours=1),
            scope="read",
        )
        result = self._call(HTTP_AUTHORIZATION=f"Bearer {token.token}")
        self.assertTrue(result["submitted"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Client: Test connector", mail.outbox[0].body)
