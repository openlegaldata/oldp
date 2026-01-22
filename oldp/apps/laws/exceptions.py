"""Custom API exceptions for law creation."""

from rest_framework.exceptions import APIException


class DuplicateLawBookError(APIException):
    """Raised when attempting to create a law book that already exists."""

    status_code = 409  # Conflict
    default_detail = "A law book with this code and revision date already exists."
    default_code = "duplicate_lawbook"


class DuplicateLawError(APIException):
    """Raised when attempting to create a law that already exists."""

    status_code = 409  # Conflict
    default_detail = "A law with this book and slug already exists."
    default_code = "duplicate_law"


class LawBookNotFoundError(APIException):
    """Raised when a referenced law book cannot be found."""

    status_code = 400  # Bad Request
    default_detail = "Could not find the specified law book."
    default_code = "lawbook_not_found"
