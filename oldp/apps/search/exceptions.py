"""Custom exceptions for search API."""

from rest_framework.exceptions import APIException


class SearchBackendUnavailable(APIException):
    """Raised when the search backend (Elasticsearch) is unreachable."""

    status_code = 503
    default_detail = "Search backend is currently unavailable. Please try again later."
    default_code = "search_backend_unavailable"


class SearchBackendTimeout(SearchBackendUnavailable):
    """Specialisation for transient timeouts that should be retried.

    Subclasses :class:`SearchBackendUnavailable` so existing
    ``except SearchBackendUnavailable`` callers keep working but
    timeout-aware handlers can branch on the more specific type.
    Wraps the response body in a dict so REST callers (incl. MCP
    consumers via OpenAPI) get a structured ``retryable: true``
    field instead of having to parse the message.
    """

    status_code = 503
    default_detail = (
        "Search timed out while warming caches. Retry the same query in a few seconds."
    )
    default_code = "search_backend_timeout"

    def __init__(self, detail=None, code=None):
        super().__init__(detail=detail, code=code)
        if isinstance(self.detail, str):
            self.detail = {
                "detail": str(self.detail),
                "retryable": True,
                "hint": (
                    "First-touch queries on large result sets read "
                    "ES segments from disk; the same query is "
                    "sub-100ms on the next attempt."
                ),
            }
