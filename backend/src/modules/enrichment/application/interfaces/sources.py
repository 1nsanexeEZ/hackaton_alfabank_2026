"""Порты источников: адаптеры к внешним мокам. Ошибки — `SourceNotFound` / `SourceUnavailable`
из домена."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.modules.enrichment.application.dto.accounting import AccountingReportsDTO
from src.modules.enrichment.application.dto.counterparty import CounterpartyRiskDTO
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO, PersonDTO
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.dto.tax import TaxProfileDTO


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


class PersonBureauSource(Protocol):
    """БКИ физлица: только с согласием самого человека (218-ФЗ)."""

    async def fetch(self, person: PersonDTO, consent_at: datetime) -> CreditHistoryDTO: ...


@dataclass(frozen=True)
class Sources:
    registry: RegistrySource
    tax: TaxSource
    bureau: CreditBureauSource
    accounting: AccountingReportsSource
    counterparty: CounterpartyRiskSource
    person_bureau: PersonBureauSource
