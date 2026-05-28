"""Utility helpers for the search app."""


def is_search_backend_error(exc: Exception) -> bool:
    """Check if an exception is an Elasticsearch connection/transport error."""
    try:
        from elasticsearch.exceptions import ConnectionError, TransportError

        return isinstance(exc, (ConnectionError, TransportError))
    except ImportError:
        return False


def is_search_backend_timeout(exc: Exception) -> bool:
    """Subset of :func:`is_search_backend_error` for transient timeouts.

    A timeout is recoverable on retry — once ES has read the relevant
    segment files into the OS page cache, the same query returns
    sub-100ms. Distinguishing this from a true outage lets MCP / web
    callers surface a ``retryable`` hint instead of asking the user to
    give up.

    Covers:
      * elasticsearch-py ``ConnectionTimeout``;
      * ``TransportError`` subclasses whose status implies a timeout
        (504 from a gateway, 408 from ES itself);
      * nested causes (urllib3 ``ReadTimeoutError`` etc.) reached via
        ``__cause__``.
    """
    try:
        from elasticsearch.exceptions import (
            ConnectionTimeout,
            TransportError,
        )
    except ImportError:
        return False
    if isinstance(exc, ConnectionTimeout):
        return True
    if isinstance(exc, TransportError):
        status = getattr(exc, "status_code", None)
        if status in (408, 504):
            return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_search_backend_timeout(cause)
    return False
