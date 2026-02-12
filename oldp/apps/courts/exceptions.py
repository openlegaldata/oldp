"""Custom exceptions for court creation API."""

from rest_framework.exceptions import APIException


class DuplicateCourtError(APIException):
    """Raised when attempting to create a court that already exists."""

    status_code = 409  # Conflict
    default_detail = "A court with this code already exists."
    default_code = "duplicate_court"


class StateNotFoundError(APIException):
    """Raised when the state cannot be resolved from the provided name."""

    status_code = 400  # Bad Request
    default_detail = "Could not resolve state from the provided name."
    default_code = "state_not_found"
