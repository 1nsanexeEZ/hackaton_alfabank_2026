from typing import Any


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    default_message: str = "Bad request"

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class BadRequestError(AppError):
    pass


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Not authenticated"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"
    default_message = "Not enough rights"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "Conflict"


class InvalidStatusTransitionError(ConflictError):
    code = "invalid_transition"
    default_message = "Status transition is not allowed"


class ValidationError(AppError):
    """Business validation failed: the request is well-formed, but the data breaks a rule."""

    status_code = 422
    code = "validation_error"
    default_message = "Validation failed"


class InfrastructureError(AppError):
    """A dependency (database, broker, external source) is unavailable."""

    status_code = 503
    code = "unavailable"
    default_message = "Service temporarily unavailable"
