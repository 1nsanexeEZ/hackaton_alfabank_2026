from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.assistant.application.interfaces.language_model import Provider
from src.modules.assistant.domain.conversation import Conversation, Mode, Role, StoredMessage
from src.modules.assistant.domain.intents import Intent
from src.modules.assistant.domain.views import ApplicationView


@dataclass(frozen=True, slots=True)
class MessageDTO:
    id: UUID
    role: Role
    text: str
    created_at: datetime
    application_id: UUID | None
    mode: Mode | None

    @classmethod
    def of(cls, message: StoredMessage) -> "MessageDTO":
        return cls(
            id=message.id,
            role=message.role,
            text=message.text,
            created_at=message.created_at,
            application_id=message.application_id,
            mode=message.mode,
        )


@dataclass(frozen=True, slots=True)
class ConversationDTO:
    id: UUID
    created_at: datetime
    messages: tuple[MessageDTO, ...]

    @classmethod
    def of(cls, conversation: Conversation) -> "ConversationDTO":
        return cls(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=tuple(MessageDTO.of(m) for m in conversation.messages),
        )


@dataclass(frozen=True, slots=True)
class AcceptedQuestionDTO:
    """A question that passed every check: it gets an answer, by stream or not."""

    conversation_id: UUID
    question: str
    application: ApplicationView | None


@dataclass(frozen=True, slots=True)
class ReplyDTO:
    message_id: UUID
    text: str
    mode: Mode
    intent: Intent
    application_id: UUID | None
    # Why the template was used: disabled, busy, timeout, unavailable, postcheck, template_only.
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationRefDTO:
    id: UUID
    number: str
    product_code: str
    status: str
    client_stage: str | None

    @classmethod
    def of(cls, app: ApplicationView) -> "ApplicationRefDTO":
        return cls(app.id, app.number, app.product_code, app.status, app.client_stage)


@dataclass(frozen=True, slots=True)
class StatusDTO:
    enabled: bool
    mode: Mode
    provider: Provider
    model: str | None
    host: str | None
    reachable: bool
    reason: str | None
