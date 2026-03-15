"""Utility helpers for the search app."""


def is_search_backend_error(exc: Exception) -> bool:
    """Check if an exception is an Elasticsearch connection/transport error."""
    try:
        from elasticsearch.exceptions import ConnectionError, TransportError

        return isinstance(exc, (ConnectionError, TransportError))
    except ImportError:
        return False
