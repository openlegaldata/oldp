"""A failed email send must not be reported to the user as sent."""

import smtplib

from django.contrib.auth.models import User
from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings

PASSWORD = "S3cure-pass-xyz!"
SENT_TEXT = "We have sent an e-mail to you for verification"
FAILED_TEXT = "We could not send the verification e-mail"


class RejectingBackend(BaseEmailBackend):
    """SMTP relay that rejects every message (e.g. as spam)."""

    def send_messages(self, email_messages):
        raise smtplib.SMTPDataError(554, b"5.7.1 Message rejected as spam")


class UnreachableBackend(BaseEmailBackend):
    """SMTP relay that cannot be reached."""

    def send_messages(self, email_messages):
        raise ConnectionRefusedError("Connection refused")


@override_settings(ACCOUNT_RATE_LIMITS=False)
class EmailSendFailureTestCase(TestCase):
    def signup(self):
        return self.client.post(
            "/accounts/signup/",
            {
                "username": "alice",
                "email": "alice@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
            follow=True,
        )

    def messages_of(self, response):
        return [str(m) for m in response.context["messages"]]

    @override_settings(
        EMAIL_BACKEND="oldp.apps.accounts.tests.test_email_sending.RejectingBackend"
    )
    def test_rejected_signup_mail_is_reported(self):
        with self.assertLogs("oldp.apps.accounts.adapters", "ERROR") as logs:
            res = self.signup()
        self.assertIn("SMTP server rejected email to alice@example.com", logs.output[0])
        self.assertTrue(User.objects.filter(username="alice").exists())
        self.assertIn("send_failed=1", res.redirect_chain[-1][0])
        html = res.content.decode()
        self.assertIn(FAILED_TEXT, html)
        self.assertNotIn(SENT_TEXT, html)
        self.assertIn("Unable to send verification email", html)
        self.assertNotIn("Confirmation email sent", " ".join(self.messages_of(res)))

    @override_settings(
        EMAIL_BACKEND="oldp.apps.accounts.tests.test_email_sending.UnreachableBackend"
    )
    def test_unreachable_relay_on_login_is_reported(self):
        User.objects.create_user("bob", "bob@example.com", PASSWORD)
        with self.assertLogs("oldp.apps.accounts.adapters", "ERROR"):
            res = self.client.post(
                "/accounts/login/",
                {"login": "bob", "password": PASSWORD},
                follow=True,
            )
        html = res.content.decode()
        self.assertIn(FAILED_TEXT, html)
        self.assertIn("Email service is temporarily unavailable", html)

    def test_successful_send_unchanged(self):
        res = self.signup()
        html = res.content.decode()
        self.assertNotIn("send_failed", res.redirect_chain[-1][0])
        self.assertIn(SENT_TEXT, html)
        self.assertIn("Confirmation email sent", html)
