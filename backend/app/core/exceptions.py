"""Unified API exception types and error response envelope.

Error response format (spec §6):
    {code, message, details, request_id}
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application error with a stable machine-readable code."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        self.status_code = status_code or self.status_code
        super().__init__(self.message)

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "request_id": request_id,
        }


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"
    message = "Request validation failed"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_error"
    message = "Authentication failed"


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"
    message = "Permission denied"


class ResourceNotFound(AppError):
    status_code = 404
    code = "resource_not_found"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Resource conflict"


class BusinessRuleError(AppError):
    status_code = 422
    code = "business_rule_violation"
    message = "Business rule violation"
