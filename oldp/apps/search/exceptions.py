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
    """

    status_code = 503
    default_detail = (
        "Search timed out while warming caches. Retry the same query in a few seconds."
    )
    default_code = "search_backend_timeout"
    retry_hint = (
        "First-touch queries on large result sets read ES segments "
        "from disk; the same query is sub-100ms on the next attempt."
    )

    def get_full_details(self):
        """Return the structured body for REST consumers.

        We override the default DRF transformation because the project
        runs every ``APIException`` through ``full_details_exception_handler``
        (``oldp/api/exceptions.py``) which calls ``get_full_details``
        and writes it back to ``self.detail``. The default traversal
        chokes on non-``ErrorDetail`` values in the dict; doing the
        shaping ourselves keeps the body clean — flat
        ``{detail, code, retryable, hint}`` — instead of nesting each
        value under ``{message, code}``.
        """
        return {
            "detail": str(self.detail)
            if isinstance(self.detail, str)
            else self.default_detail,
            "code": self.default_code,
            "retryable": True,
            "hint": self.retry_hint,
        }
