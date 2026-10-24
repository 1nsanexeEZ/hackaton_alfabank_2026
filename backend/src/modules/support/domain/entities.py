from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.support.domain.enums import Side


@dataclass(frozen=True, slots=True)
class TicketMessage:
    """One message of the chat. Messages are never edited or deleted."""

    id: UUID
    author_id: UUID
    side: Side
    text: str
    created_at: datetime
