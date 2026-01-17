"""Custom exceptions for case creation API."""

from rest_framework.exceptions import APIException


class DuplicateCaseError(APIException):
    """Raised when attempting to create a case that already exists."""

    status_code = 409  # Conflict
    default_detail = "A case with this court and file number already exists."
    default_code = "duplicate_case"


class CourtNotFoundError(APIException):
    """Raised when the court cannot be resolved from the provided name."""

    status_code = 400  # Bad Request
    default_detail = "Could not resolve court from the provided name."
    default_code = "court_not_found"
