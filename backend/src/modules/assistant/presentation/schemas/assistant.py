from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.assistant.domain.conversation import MAX_QUESTION_CHARS
from src.modules.assistant.domain.intents import Intent


class AssistantQuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    application_id: UUID | None = Field(
        default=None,
        description="The application the question is about; without it the only active "
        "application of the user is taken when the question needs one",
    )


class AssistantConversationCreatedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class AssistantMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime
    application_id: UUID | None
    mode: Literal["llm", "rules"] | None


class AssistantConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    messages: list[AssistantMessageOut]


class AssistantReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    text: str
    mode: Literal["llm", "rules"]
    intent: Intent
    application_id: UUID | None
    fallback_reason: str | None = Field(
        description="Why the template answered: template_only, disabled, busy, timeout, "
        "unavailable, postcheck; null — the model's answer passed the post-check"
    )


class AssistantApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    product_code: str
    status: str
    client_stage: str | None


class AssistantStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool = Field(description="A model is configured and allowed")
    mode: Literal["llm", "rules"] = Field(description="Who answers now: the model or templates")
    provider: Literal["off", "local", "api"]
    model: str | None
    host: str | None
    reachable: bool = Field(description="The server answers and serves the model")
    reason: str | None = Field(description="Why the model is off")
