"""MCP-specific rate throttle classes.

Provides throttling for anonymous and authenticated MCP requests. Anonymous
requests from Anthropic's infrastructure IPs share a single bucket to prevent
one heavy user from blocking all Claude connector users. Authenticated
requests share the per-user REST API budget (see ``MCPUserThrottle``).

Throttle hits are logged at ``warning`` level under ``oldp.mcp.throttle``
so operators can alert on abuse.
"""

import functools
import ipaddress
import logging

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

from oldp.api.throttling import TokenUserRateThrottle

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


class MCPUserThrottle(TokenUserRateThrottle):
    """Per-user throttle for authenticated MCP requests.

    Authenticated MCP calls share one budget with the REST API: the same
    per-user cache bucket and the same rate resolution (per-token override,
    enriched tier, default ``user`` rate) as ``TokenUserRateThrottle``. A
    request to either surface consumes the same quota, and the account
    dashboard shows the combined consumption.
    """

    def throttle_failure(self):
        """Log rate-limit hits with the applied rate and throttle key."""
        logger.warning(
            "mcp_throttle_hit scope=%s rate=%s key=%s",
            self.scope,
            getattr(self, "rate", None) or self.get_rate(),
            getattr(self, "key", None),
        )
        return super().throttle_failure()
