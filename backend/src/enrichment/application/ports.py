"""Порты модуля: источники (адаптеры к внешним мокам) и хранилище снимков."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.enrichment.domain.snapshot import EnrichmentSnapshot
from src.enrichment.facade import CreditHistoryDTO, RegistryExtractDTO, TaxProfileDTO


class SourceError(Exception):
    """Ошибка обращения к источнику. `kind` — timeout | unavailable | not_found | bad_response."""

    def __init__(self, kind: str, message: str, *, attempts: int = 1) -> None:
        super().__init__(message)
        self.kind = kind
        self.attempts = attempts


class SourceNotFound(SourceError):
    def __init__(self, message: str = "not found", *, attempts: int = 1) -> None:
        super().__init__("not_found", message, attempts=attempts)


class SourceUnavailable(SourceError):
    pass


class RegistrySource(Protocol):
    async def fetch(self, inn: str) -> RegistryExtractDTO: ...


class TaxSource(Protocol):
    async def fetch(self, inn: str) -> TaxProfileDTO: ...


class CreditBureauSource(Protocol):
    async def fetch(self, inn: str, consent_at: datetime) -> CreditHistoryDTO: ...


class EnrichmentRepository(Protocol):
    async def add(self, snapshot: EnrichmentSnapshot) -> None: ...

    async def get_by_command(self, command_event_id: UUID) -> EnrichmentSnapshot | None: ...

    async def latest_for_application(self, application_id: UUID) -> EnrichmentSnapshot | None: ...
