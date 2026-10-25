"""A conversation with the assistant: it belongs to the account that started it."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

Role = Literal["user", "assistant"]
# llm — the model worded the answer and it passed the post-check; rules — the template.
Mode = Literal["llm", "rules"]

MAX_QUESTION_CHARS = 1000


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: UUID
    role: Role
    text: str
    created_at: datetime
    application_id: UUID | None = None
    intent: str | None = None
    mode: Mode | None = None


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    owner_id: UUID
    created_at: datetime
    messages: tuple[StoredMessage, ...] = ()
