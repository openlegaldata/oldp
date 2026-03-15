"""Custom exceptions for search API."""

from rest_framework.exceptions import APIException


class SearchBackendUnavailable(APIException):
    """Raised when the search backend (Elasticsearch) is unreachable."""

    status_code = 503
    default_detail = "Search backend is currently unavailable. Please try again later."
    default_code = "search_backend_unavailable"
