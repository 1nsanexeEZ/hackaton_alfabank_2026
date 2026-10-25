"""Assistant errors as HTTP responses, in the same shape as core AppError:
`{code, message}`; too many questions is 429 with `Retry-After`."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.exceptions.exceptions import AppError, NotFoundError, ValidationError
from src.core.exceptions.handlers import app_error_handler
from src.modules.assistant.domain import exceptions as errors

RESPONSES: dict[type[errors.AssistantError], type[AppError]] = {
    errors.QuestionRejectedError: ValidationError,
    errors.ConversationNotFoundError: NotFoundError,
    errors.ApplicationNotFoundError: NotFoundError,
}


async def assistant_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, errors.AssistantError)
    if isinstance(exc, errors.TooManyQuestionsError):
        return JSONResponse(
            status_code=429,
            content={"code": "too_many_requests", "message": exc.message},
            headers={"Retry-After": str(exc.retry_after_s)},
        )
    return await app_error_handler(request, RESPONSES[type(exc)](exc.message, exc.details))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(errors.AssistantError, assistant_error_handler)
