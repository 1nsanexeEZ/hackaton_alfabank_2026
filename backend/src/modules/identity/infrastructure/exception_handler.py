"""Identity errors as HTTP responses, in the same shape as core AppError:
`{code, message}`, a 401 with `WWW-Authenticate`."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.exceptions.exceptions import (
    AppError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.core.exceptions.handlers import app_error_handler
from src.modules.identity.domain import exceptions as errors

RESPONSES: dict[type[errors.IdentityError], type[AppError]] = {
    errors.InvalidCredentialsError: UnauthorizedError,
    errors.InvalidTokenError: UnauthorizedError,
    errors.TokenExpiredError: UnauthorizedError,
    errors.CurrentAccountNotFoundError: UnauthorizedError,
    errors.AccountNotFoundError: NotFoundError,
    errors.RoleNotFoundError: NotFoundError,
    errors.DemoAccountNotFoundError: NotFoundError,
    errors.UnknownRoleError: BadRequestError,
    errors.OrphanedPoliciesError: BadRequestError,
    errors.LoginRequiredError: BadRequestError,
    errors.SelfDeletionError: BadRequestError,
    errors.EmptyNameError: BadRequestError,
    errors.NameLockedError: ValidationError,
    errors.RoleAlreadyExistsError: ConflictError,
    errors.RoleInUseError: ConflictError,
    errors.LoginTakenError: ConflictError,
}


def to_app_error(exc: errors.IdentityError) -> AppError:
    return RESPONSES[type(exc)](exc.message, exc.details)


async def identity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, errors.IdentityError)
    return await app_error_handler(request, to_app_error(exc))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(errors.IdentityError, identity_error_handler)
