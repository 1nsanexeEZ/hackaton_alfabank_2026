"""Хранилище снимков."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot


class EnrichmentRepository(Protocol):
    async def add(self, snapshot: EnrichmentSnapshot) -> None: ...

    async def get_by_command(self, command_event_id: UUID) -> EnrichmentSnapshot | None: ...

    async def latest_for_application(self, application_id: UUID) -> EnrichmentSnapshot | None: ...
