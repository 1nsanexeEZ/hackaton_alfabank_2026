class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    default_message: str = "Bad request"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
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
