"""Assistant errors, without HTTP: `infrastructure/exception_handler.py` maps them."""

from typing import Any


class AssistantError(Exception):
    default_message = "Assistant error"

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class QuestionRejectedError(AssistantError):
    default_message = "The question is empty or longer than 1000 characters"


class ConversationNotFoundError(AssistantError):
    """No such conversation, or it belongs to someone else (same answer for both)."""

    default_message = "Conversation not found"


class ApplicationNotFoundError(AssistantError):
    """No such application, or the viewer may not see it (same answer for both)."""

    default_message = "Application not found"


class TooManyQuestionsError(AssistantError):
    default_message = "Too many questions, try again later"

    def __init__(self, retry_after_s: int) -> None:
        super().__init__(details={"retry_after_s": retry_after_s})
        self.retry_after_s = retry_after_s
