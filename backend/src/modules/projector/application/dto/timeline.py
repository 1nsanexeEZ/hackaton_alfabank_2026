"""The timeline of an application."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.modules.projector.domain.enums import Audience, EntryKind


@dataclass(frozen=True, slots=True)
class TimelineEntryDTO:
    id: UUID
    application_id: UUID
    at: datetime
    kind: EntryKind
    title: str
    audience: Audience
    details: dict[str, Any]
