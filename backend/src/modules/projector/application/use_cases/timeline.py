"""Read of the timeline of an application."""

from typing import cast
from uuid import UUID

from src.modules.projector.application.dto.timeline import TimelineEntryDTO
from src.modules.projector.application.interfaces.repositories import ReadModelQueries
from src.modules.projector.domain.enums import Audience, EntryKind
from src.modules.projector.domain.timeline import CLIENT


class GetTimelineUseCase:
    def __init__(self, read_models: ReadModelQueries) -> None:
        self._read_models = read_models

    async def execute(self, application_id: UUID, audience: Audience) -> list[TimelineEntryDTO]:
        """audience=client returns client entries only; bank gets everything."""
        entries = await self._read_models.timeline_of(
            application_id, client_only=audience == CLIENT
        )
        return [
            TimelineEntryDTO(
                id=entry.id,
                application_id=entry.application_id,
                at=entry.at,
                kind=cast(EntryKind, entry.kind),
                title=entry.title,
                audience=cast(Audience, entry.audience),
                details=dict(entry.details or {}),
            )
            for entry in entries
        ]
