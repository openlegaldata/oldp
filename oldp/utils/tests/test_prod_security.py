"""Regression tests for production transport-security settings.

Asserts the production configuration marks the session and CSRF cookies Secure
and redirects to HTTPS, so authenticated cookies are never sent over plaintext.
These are plain class attributes (not env-configurable ``values.Value``s) so they
cannot be accidentally disabled per-deployment. HSTS is intentionally not set
(disabled at the Cloudflare edge).
"""

from django.test import SimpleTestCase

from oldp.settings import ProdConfiguration


class ProdTransportSecurityTest(SimpleTestCase):
    def test_session_cookie_secure(self):
        self.assertIs(ProdConfiguration.SESSION_COOKIE_SECURE, True)

    def test_csrf_cookie_secure(self):
        self.assertIs(ProdConfiguration.CSRF_COOKIE_SECURE, True)

    def test_ssl_redirect_enabled(self):
        self.assertIs(ProdConfiguration.SECURE_SSL_REDIRECT, True)

    def test_hsts_not_emitted_from_django(self):
        # HSTS is disabled at the Cloudflare edge; Django must not emit it
        # either. Default is 0 / unset.
        self.assertIn(getattr(ProdConfiguration, "SECURE_HSTS_SECONDS", 0), (0, None))
