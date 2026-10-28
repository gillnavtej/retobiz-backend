from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_handler
from rest_framework.response import Response
from django.http import Http404


class DomainError(Exception):
    code = "ERROR"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "Error"

    def __init__(self, message=None, details=None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}


class InsufficientStock(DomainError):
    code = "INSUFFICIENT_STOCK"
    http_status = status.HTTP_409_CONFLICT


class IdempotencyConflict(DomainError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = status.HTTP_409_CONFLICT
    message = "This transaction ID was already used with a different request body."


class DuplicateBarcode(DomainError):
    code = "DUPLICATE_BARCODE"
    http_status = status.HTTP_409_CONFLICT
    message = "A product with this barcode already exists in this store."


class InvalidOverride(DomainError):
    code = "INVALID_OVERRIDE"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


class BusinessValidationError(DomainError):
    code = "VALIDATION_ERROR"
    http_status = status.HTTP_400_BAD_REQUEST


def _body(code, message, details=None):
    return {"error": {"code": code, "message": message, "details": details or {}}}


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response(_body(exc.code, exc.message, exc.details), status=exc.http_status)
    if isinstance(exc, Http404):
        exc = NotFound()
    response = drf_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, ValidationError):
        return Response(
            _body("VALIDATION_ERROR", "Invalid request.", response.data),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        code = "AUTHENTICATION_FAILED"
    elif isinstance(exc, PermissionDenied):
        code = "PERMISSION_DENIED"
    elif isinstance(exc, NotFound):
        code = "NOT_FOUND"
    elif isinstance(exc, Throttled):
        code = "THROTTLED"
    else:
        code = getattr(exc, "default_code", "ERROR").upper()
    message = response.data.get("detail", "Error") if isinstance(response.data, dict) else "Error"
    return Response(_body(code, str(message)), status=response.status_code, headers=dict(response.headers))
