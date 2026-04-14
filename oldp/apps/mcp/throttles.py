"""MCP-specific rate throttle classes.

Provides separate throttling for anonymous and authenticated MCP requests.
Anonymous requests from Anthropic's infrastructure IPs share a single bucket
to prevent one heavy user from blocking all Claude connector users.

Throttle hits are logged at ``warning`` level under ``oldp.mcp.throttle``
so operators can alert on abuse.
"""

import functools
import ipaddress
import logging

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger("oldp.mcp.throttle")

# Anthropic's published outbound CIDR for MCP tool calls
# https://docs.anthropic.com/en/api/ip-addresses
ANTHROPIC_CIDRS = [
    ipaddress.ip_network("160.79.104.0/21"),
]


@functools.lru_cache(maxsize=10_000)
def _is_anthropic_ip(ip_str: str) -> bool:
    """Return True if ``ip_str`` belongs to Anthropic's outbound IP range.

    The result is memoised so we avoid re-parsing the same IP on every
    request. Bad input (``None``, unparseable strings) is memoised as
    ``False`` rather than raising.
    """
    if not ip_str:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except (ValueError, TypeError):
        return False
    return any(ip in cidr for cidr in ANTHROPIC_CIDRS)


class MCPAnonThrottle(SimpleRateThrottle):
    """Throttle for anonymous MCP requests.

    Anthropic infrastructure IPs share a single bucket (all anonymous Claude
    connector users come from the same IP pool). Other anonymous clients get
    per-IP buckets.
    """

    scope = "mcp_anon"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None  # Authenticated users handled by MCPUserThrottle
        ident = self.get_ident(request)
        if _is_anthropic_ip(ident):
            return "throttle_mcp_anthropic_anon"
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def get_rate(self):
        return getattr(settings, "MCP_ANTHROPIC_ANON_RATE", "500/hour")

    def throttle_failure(self):
        """Log rate-limit hits so operators can alert on sustained abuse."""
        logger.warning("mcp_throttle_hit scope=%s rate=%s", self.scope, self.get_rate())
        return super().throttle_failure()


class MCPUserThrottle(SimpleRateThrottle):
    """Per-user throttle for authenticated MCP requests."""

    scope = "mcp_user"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None  # Anonymous users handled by MCPAnonThrottle
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }

    def get_rate(self):
        return getattr(settings, "MCP_USER_RATE", "1000/hour")

    def throttle_failure(self):
        """Log rate-limit hits with the user pk for accountability."""
        logger.warning("mcp_throttle_hit scope=%s rate=%s", self.scope, self.get_rate())
        return super().throttle_failure()
