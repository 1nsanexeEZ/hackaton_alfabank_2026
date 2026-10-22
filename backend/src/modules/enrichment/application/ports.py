"""Порты модуля: источники (адаптеры к внешним мокам) и хранилище снимков."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot
from src.modules.enrichment.facade import (
    AccountingReportsDTO,
    CounterpartyRiskDTO,
    CreditHistoryDTO,
    RegistryExtractDTO,
    TaxProfileDTO,
)


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


class AccountingReportsSource(Protocol):
    """ГИР БО: бухотчётность юрлица."""

    async def fetch(self, inn: str) -> AccountingReportsDTO: ...


class CounterpartyRiskSource(Protocol):
    """Контур: суды, приставы, банкротство."""

    async def fetch(self, inn: str) -> CounterpartyRiskDTO: ...


@dataclass(frozen=True, slots=True)
class PersonQuery:
    """Физлицо для запроса кредитной истории; `company_inn` — компания, по заявке которой
    спрашиваем."""

    last_name: str
    first_name: str
    middle_name: str | None
    company_inn: str


class PersonBureauSource(Protocol):
    """БКИ физлица: только с согласием самого человека (218-ФЗ)."""

    async def fetch(self, person: PersonQuery, consent_at: datetime) -> CreditHistoryDTO: ...


class EnrichmentRepository(Protocol):
    async def add(self, snapshot: EnrichmentSnapshot) -> None: ...

    async def get_by_command(self, command_event_id: UUID) -> EnrichmentSnapshot | None: ...

    async def latest_for_application(self, application_id: UUID) -> EnrichmentSnapshot | None: ...
