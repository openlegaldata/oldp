import os
from unittest import skipIf

from django.core import mail
from django.test import LiveServerTestCase
from django.urls import reverse

from oldp.apps.contact.forms import ContactForm, ReportContentForm

# A name/message pair that satisfies the anti-spam whitespace minimums
# (see oldp.apps.contact.forms): name needs >=1 whitespace, message >=5.
_VALID_NAME = "My name"
_VALID_MESSAGE = "My message has many words separated by spaces"


class ContactViewsTestCase(LiveServerTestCase):
    def test_form(self):
        res = self.client.get(reverse("contact:form"))

        self.assertTemplateUsed(res, "contact/form.html")

        self.assertContains(res, "csrfmiddlewaretoken")

    @skipIf("DJANGO_EMAIL_HOST" in os.environ, "SMTP host is not configured.")
    def test_form_submit(self):
        res = self.client.post(
            reverse("contact:form"),
            {
                "name": _VALID_NAME,
                "email": "my@email.com",
                "message": _VALID_MESSAGE,
                "captcha": "12",
            },
        )

        self.assertRedirects(res, reverse("contact:thankyou"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(_VALID_NAME in mail.outbox[0].subject)

    def test_thank_you(self):
        res = self.client.get(reverse("contact:thankyou"))

        self.assertTemplateUsed(res, "contact/thankyou.html")


class ContactFormValidationTestCase(LiveServerTestCase):
    """The whitespace heuristic blocks drive-by spam where the name is a
    single token or the message is a single URL/word. We assert the error
    is generic so the threshold isn't leaked to scripted callers.
    """

    def _base_payload(self, **overrides):
        data = {
            "name": _VALID_NAME,
            "email": "my@email.com",
            "message": _VALID_MESSAGE,
            "captcha": 12,
        }
        data.update(overrides)
        return data

    def test_name_without_whitespace_rejected(self):
        form = ContactForm(self._base_payload(name="Singleword"))
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertEqual(form.errors["name"], ["Invalid input."])

    def test_message_with_too_few_whitespaces_rejected(self):
        form = ContactForm(self._base_payload(message="too short"))
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)
        self.assertEqual(form.errors["message"], ["Invalid input."])

    def test_valid_name_and_message_pass(self):
        form = ContactForm(self._base_payload())
        self.assertTrue(form.is_valid(), msg=form.errors)


class ReportContentFormValidationTestCase(LiveServerTestCase):
    """Same anti-spam heuristic on the report-content form."""

    def _base_payload(self, **overrides):
        data = {
            "source": "https://example.com/case/1",
            "subject": "Privacy",
            "name": _VALID_NAME,
            "email": "my@email.com",
            "message": _VALID_MESSAGE,
        }
        data.update(overrides)
        return data

    def test_name_without_whitespace_rejected(self):
        form = ReportContentForm(self._base_payload(name="Singleword"))
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertEqual(form.errors["name"], ["Invalid input."])

    def test_message_with_too_few_whitespaces_rejected(self):
        form = ReportContentForm(self._base_payload(message="too short"))
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)
        self.assertEqual(form.errors["message"], ["Invalid input."])

    def test_valid_name_and_message_pass(self):
        form = ReportContentForm(self._base_payload())
        self.assertTrue(form.is_valid(), msg=form.errors)
