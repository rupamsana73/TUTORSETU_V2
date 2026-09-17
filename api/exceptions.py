"""Consistent API error envelope — never leak internals."""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("tutorsetu")


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data
        if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
            message = str(detail["detail"])
            errors = {}
        else:
            message = "Unable to process your request."
            errors = detail if isinstance(detail, (dict, list)) else {}
        response.data = {
            "success": False,
            "message": message,
            "errors": errors,
        }
        return response
    # Unhandled exception — log it, return a safe generic error.
    logger.exception("Unhandled API exception", exc_info=exc)
    return Response(
        {"success": False, "message": "Something went wrong. Please try again later.", "errors": {}},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
