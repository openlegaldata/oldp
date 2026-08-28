"""Regression tests for production transport-security settings.

Asserts the production configuration marks the session and CSRF cookies Secure
and redirects to HTTPS by default, so authenticated cookies are never sent over
plaintext. The settings are ``values.BooleanValue(True)`` — secure by default,
but env-overridable (``DJANGO_SESSION_COOKIE_SECURE`` etc.) so a non-HTTPS
deployment (the plain-HTTP stage) can opt out; disabling requires an explicit
per-environment override. HSTS is intentionally not set (disabled at the
Cloudflare edge).
"""

from configurations.values import BooleanValue
from django.test import SimpleTestCase

from oldp.settings import ProdConfiguration


class ProdTransportSecurityTest(SimpleTestCase):
    def test_session_cookie_secure_by_default(self):
        value = ProdConfiguration.SESSION_COOKIE_SECURE
        self.assertIsInstance(value, BooleanValue)  # env-overridable
        self.assertIs(value.default, True)  # ...but secure by default

    def test_csrf_cookie_secure_by_default(self):
        value = ProdConfiguration.CSRF_COOKIE_SECURE
        self.assertIsInstance(value, BooleanValue)
        self.assertIs(value.default, True)

    def test_ssl_redirect_enabled_by_default(self):
        value = ProdConfiguration.SECURE_SSL_REDIRECT
        self.assertIsInstance(value, BooleanValue)
        self.assertIs(value.default, True)

    def test_hsts_not_emitted_from_django(self):
        # HSTS is disabled at the Cloudflare edge; Django must not emit it
        # either. Default is 0 / unset.
        self.assertIn(getattr(ProdConfiguration, "SECURE_HSTS_SECONDS", 0), (0, None))
