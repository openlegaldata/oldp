"""Settings-derived values that markdown pages can reference as ``{{ key }}``.

Pages such as the API page mention numbers and URLs that are configured in
Django settings (rate limits, the MCP endpoint, ...). Writing them into the
markdown means the page goes stale whenever a setting changes. Instead a page
writes a placeholder, e.g. ``{{ limits.user.count }}``, and the renderer fills
it from :func:`page_variables` at request time.

This is deliberately *not* the Django template engine: a placeholder is a plain
lookup in a fixed whitelist, with no tags, filters or expressions, so a markdown
file (which may come from a separately mounted directory) can only insert the
values listed here. Unknown keys are left in the output unchanged and logged,
so a typo is visible on the page instead of rendering as an empty string.

Placeholders are swapped for an alphanumeric sentinel *before* the markdown is
parsed (:func:`protect_placeholders`) and for their values *after* it
(:func:`fill_placeholders`). Otherwise syntax highlighting in code blocks would
split ``{{ urls.api }}`` into several ``<span>`` tokens and the placeholder
would no longer be found in the HTML.
"""

import logging
import re

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import formats
from django.utils.html import escape
from django.utils.translation import gettext
from rest_framework.settings import api_settings

import oldp

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z0-9_]+(?:\.[a-z0-9_]+)*)\s*\}\}")

# Sentinel standing in for a placeholder while markdown and Pygments process the
# page: letters and hex digits only, so no lexer splits it and markdown leaves
# it alone. The key is hex-encoded, e.g. ``OLDPVAR75726c732e617069Z``.
_SENTINEL_PREFIX = "OLDPVAR"
SENTINEL_RE = re.compile(_SENTINEL_PREFIX + r"([0-9a-f]+)Z")

# Named routes exposed as ``urls.<key>`` (absolute, based on SITE_URL).
_URL_NAMES = {
    "api": ("api-root", {}),
    "api_docs": ("schema-redoc", {}),
    "api_swagger": ("schema-swagger-ui", {}),
    "api_schema": ("schema-json", {"format": ".json"}),
    "whoami": ("api-whoami", {}),
    "mcp": ("mcp_endpoint", {}),
    "tokens": ("account_api", {}),
    "signup": ("account_signup", {}),
    "profile": ("account_profile", {}),
}


def _period_name(period: str) -> str:
    """Translated singular name of a DRF rate period (``"hour"`` -> ``"Stunde"``)."""
    names = {
        "s": gettext("second"),
        "m": gettext("minute"),
        "h": gettext("hour"),
        "d": gettext("day"),
    }
    return names.get(period[:1], period)


def rate_variables(name: str, rate: str | None) -> dict[str, str]:
    """Placeholders for one DRF-style rate such as ``"5000/hour"``.

    Args:
        name: Key under ``limits.`` (e.g. ``"user"``).
        rate: The rate string, or ``None`` if the rate is not configured.

    Returns:
        ``limits.<name>.count`` (localized, with thousands separator),
        ``limits.<name>.period`` (translated) and ``limits.<name>.raw``; empty
        if ``rate`` is unset or malformed.
    """
    if not rate:
        return {}
    try:
        num, period = rate.split("/")
        count = int(num)
    except ValueError:
        logger.warning("page variable limits.%s: cannot parse rate %r", name, rate)
        return {}
    return {
        f"limits.{name}.count": formats.number_format(
            count, use_l10n=True, force_grouping=True
        ),
        f"limits.{name}.period": _period_name(period),
        f"limits.{name}.raw": rate,
    }


def _absolute_url(url_name: str, kwargs: dict) -> str | None:
    try:
        path = reverse(url_name, kwargs=kwargs or None)
    except NoReverseMatch:
        return None
    return f"{(getattr(settings, 'SITE_URL', '') or '').rstrip('/')}{path}"


def page_variables() -> dict[str, str]:
    """All values a markdown page may reference, keyed by placeholder name.

    Computed per call (cheap: a handful of ``reverse()`` calls) so the values
    follow the active language and any settings override.
    """
    variables: dict[str, str] = {"version": oldp.__version__}

    rates = api_settings.DEFAULT_THROTTLE_RATES or {}
    for name in ("anon", "user", "enriched"):
        variables.update(rate_variables(name, rates.get(name)))
    variables.update(
        rate_variables("mcp_anon", getattr(settings, "MCP_ANTHROPIC_ANON_RATE", None))
    )

    variables["urls.site"] = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    for key, (url_name, kwargs) in _URL_NAMES.items():
        url = _absolute_url(url_name, kwargs)
        if url:
            variables[f"urls.{key}"] = url
    return variables


def protect_placeholders(text: str) -> str:
    """Swap ``{{ key }}`` placeholders in markdown source for sentinels.

    Run before markdown parsing; :func:`fill_placeholders` reverses it.
    """
    return PLACEHOLDER_RE.sub(
        lambda m: f"{_SENTINEL_PREFIX}{m.group(1).encode().hex()}Z", text
    )


def has_placeholders(text: str) -> bool:
    """True if ``text`` contains a placeholder or a sentinel for one."""
    return "{{" in text or _SENTINEL_PREFIX in text


def fill_placeholders(text: str, variables: dict[str, str], *, html: bool) -> str:
    """Replace placeholders (and their sentinels) in ``text`` with their values.

    Args:
        text: Rendered page HTML (or the plain-text title).
        variables: Mapping from :func:`page_variables`.
        html: If true, values are HTML-escaped before insertion.

    Returns:
        The text with known placeholders replaced; unknown ones are restored to
        ``{{ key }}`` as written.
    """
    if not has_placeholders(text):
        return text

    def _value(key: str, original: str) -> str:
        if key not in variables:
            logger.warning("unknown page variable {{ %s }} left as is", key)
            return escape(original) if html else original
        value = variables[key]
        return escape(value) if html else value

    def _from_sentinel(match: re.Match) -> str:
        try:
            key = bytes.fromhex(match.group(1)).decode()
        except ValueError:
            return match.group(0)
        return _value(key, "{{ %s }}" % key)

    text = SENTINEL_RE.sub(_from_sentinel, text)
    return PLACEHOLDER_RE.sub(lambda m: _value(m.group(1), m.group(0)), text)
