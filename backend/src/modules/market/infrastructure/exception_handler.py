"""Market errors as HTTP responses, in the same shape as core AppError: `{code, message}`."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.exceptions.exceptions import (
    AppError,
    ConflictError,
    InvalidStatusTransitionError,
    NotFoundError,
    ValidationError,
)
from src.core.exceptions.handlers import app_error_handler
from src.modules.market.domain import exceptions as errors

RESPONSES: dict[type[errors.MarketError], type[AppError]] = {
    errors.InvalidKeyRateError: ValidationError,
    errors.KeyRateDateTakenError: ConflictError,
    errors.KeyRateInForceError: InvalidStatusTransitionError,
    errors.KeyRateNotFoundError: NotFoundError,
}


async def market_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, errors.MarketError)
    return await app_error_handler(request, RESPONSES[type(exc)](exc.message, exc.details))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(errors.MarketError, market_error_handler)
