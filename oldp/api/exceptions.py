from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


def full_details_exception_handler(exc, context):
    """
    This overrides the default exception handler to
    include the human-readable message AND the error code
    so that clients can respond programmatically.
    """
    if isinstance(exc, APIException):
        exc.detail = exc.get_full_details()

    return exception_handler(exc, context)
