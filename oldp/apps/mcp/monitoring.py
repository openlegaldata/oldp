"""Logging and monitoring helpers for MCP tools.

Provides a `@log_tool_call` decorator that records every MCP tool invocation
with its duration, authentication state, and outcome. Logs are emitted under
the ``oldp.mcp.tools`` logger so operators can configure their own handlers
for structured observability (file logs, Prometheus via log parsing,
CloudWatch, Sentry, etc.).

The decorator is designed to:

* be cheap on the hot path (a single ``time.perf_counter`` sample and a
  lightweight f-string),
* never raise when the wrapped tool raises — the tool's own exception is
  always re-raised so the MCP runtime can map it to a tool-level error,
* redact or summarise potentially large arguments (content text, query
  strings over 200 characters) so logs stay manageable.

The module also exposes ``get_auth_state(request)`` which returns a short
string ("anon", "user:<pk>", or "oauth:<client_id>") used both for logs and
for test assertions.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("oldp.mcp.tools")

# Maximum length of a stringified argument in logs before it is truncated.
# Longer payloads (like big search queries) are replaced with a length summary.
_MAX_ARG_REPR_LEN = 200


def get_auth_state(request: Any) -> str:
    """Return a compact auth-state string for logging.

    Args:
        request: The Django/DRF request associated with the MCP call. May be
            ``None`` or a ``SimpleNamespace`` when the tool is invoked outside
            a real HTTP context (e.g. during unit tests).

    Returns:
        One of:
            * ``"anon"`` — no authenticated user
            * ``"user:<pk>"`` — authenticated via session or token
            * ``"oauth:<client_id>"`` — authenticated via OAuth2 access token
    """
    user = getattr(request, "user", None)
    auth = getattr(request, "auth", None)

    # OAuth2 tokens expose a related application with a client_id
    client_id = getattr(getattr(auth, "application", None), "client_id", None)
    if client_id:
        return f"oauth:{client_id}"

    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.pk}"

    return "anon"


def _summarise_value(value: Any) -> str:
    """Return a short repr of a tool argument suitable for log output."""
    if value is None:
        return "None"
    if isinstance(value, (int, float, bool)):
        return repr(value)
    if isinstance(value, str):
        if len(value) <= _MAX_ARG_REPR_LEN:
            return repr(value)
        return f"<str len={len(value)}>"
    if isinstance(value, (list, tuple, set)):
        return f"<{type(value).__name__} len={len(value)}>"
    if isinstance(value, dict):
        return f"<dict keys={len(value)}>"
    return f"<{type(value).__name__}>"


def _summarise_result(result: Any) -> str:
    """Return a short repr of the tool result for log output.

    Focuses on the fields that matter for monitoring: number of results,
    whether it was an error, and the presence of a ``total`` counter. The
    full payload is never logged because cases/laws can be very large.
    """
    if isinstance(result, dict):
        if "error" in result:
            return f"error={result['error'][:80]!r}"
        parts = []
        if "total" in result:
            parts.append(f"total={result['total']}")
        if "results" in result and isinstance(result["results"], list):
            parts.append(f"results={len(result['results'])}")
        if "found" in result:
            parts.append(f"found={result['found']}")
        if not parts:
            parts.append(f"keys={len(result)}")
        return " ".join(parts)
    if isinstance(result, list):
        return f"list len={len(result)}"
    return f"<{type(result).__name__}>"


def log_tool_call(fn: Callable) -> Callable:
    """Decorator that logs MCP tool invocations with timing and outcome.

    Usage on an :class:`MCPToolset` method::

        class CaseTools(MCPToolset):
            @log_tool_call
            def get_case(self, case_id: int = 0) -> dict:
                ...

    The decorator reads ``self.request`` (populated by ``django-mcp-server``)
    to determine the auth state. Timing is measured with
    ``time.perf_counter()``. Exceptions from the wrapped tool are re-raised
    unchanged after being logged at ``error`` level.
    """

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        tool_name = fn.__name__
        auth_state = get_auth_state(getattr(self, "request", None))
        start = time.perf_counter()

        # Build a compact args summary (positional + keyword).
        arg_summary = ", ".join(_summarise_value(a) for a in args)
        kwarg_summary = ", ".join(
            f"{k}={_summarise_value(v)}" for k, v in sorted(kwargs.items())
        )
        call_summary = ", ".join(p for p in (arg_summary, kwarg_summary) if p)

        logger.info(
            "mcp_tool_start tool=%s auth=%s args=%s",
            tool_name,
            auth_state,
            call_summary or "-",
        )

        try:
            result = fn(self, *args, **kwargs)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000.0
            logger.error(
                "mcp_tool_error tool=%s auth=%s duration_ms=%.1f error=%s",
                tool_name,
                auth_state,
                duration_ms,
                exc.__class__.__name__,
                exc_info=True,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            "mcp_tool_end tool=%s auth=%s duration_ms=%.1f result=%s",
            tool_name,
            auth_state,
            duration_ms,
            _summarise_result(result),
        )
        return result

    return wrapper
