"""Regression tests for production transport-security settings.

The Secure-cookie / SSL-redirect settings MUST be defined on
``BaseConfiguration``, not ``ProdConfiguration``. The deployed config is
``ProdDEConfiguration(BaseDEConfiguration, ProdConfiguration)``; django-
configurations injects Django's (insecure) defaults onto the DE classes, which
precede ``ProdConfiguration`` in the MRO and shadow anything set there — so on
``ProdConfiguration`` these silently resolve to ``False`` for the deployed app.
Values on ``BaseConfiguration`` propagate correctly. See the note in
``oldp/settings.py``. (The effective ``True`` in the deployed ProdDE config is
verified during deployment; here we lock in the source-of-truth + test safety.)
"""

import inspect

from django.conf import settings
from django.test import SimpleTestCase

from oldp.settings import BaseConfiguration, ProdConfiguration

_SETTINGS = ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT")


class TransportSecurityTest(SimpleTestCase):
    def test_defined_secure_on_baseconfiguration(self):
        src = inspect.getsource(BaseConfiguration)
        for name in _SETTINGS:
            self.assertIn(
                f"{name} = values.BooleanValue(True)",
                src,
                f"{name} must be a secure-by-default BooleanValue on BaseConfiguration",
            )

    def test_not_assigned_on_prodconfiguration(self):
        # On ProdConfiguration they are shadowed/inert for the deployed DE config.
        src = inspect.getsource(ProdConfiguration)
        for name in _SETTINGS:
            self.assertNotIn(
                f"{name} =",
                src,
                f"{name} must not be assigned on ProdConfiguration (it would be inert)",
            )

    def test_disabled_under_testconfiguration(self):
        # Tests run under TestConfiguration; these must be off so the test client
        # isn't 301-redirected to https and cookies work over plain HTTP.
        for name in _SETTINGS:
            self.assertIs(
                getattr(settings, name), False, f"{name} must be False in tests"
            )

    def test_hsts_not_emitted(self):
        # HSTS is disabled at the Cloudflare edge; Django must not emit it.
        self.assertIn(getattr(settings, "SECURE_HSTS_SECONDS", 0), (0, None))
