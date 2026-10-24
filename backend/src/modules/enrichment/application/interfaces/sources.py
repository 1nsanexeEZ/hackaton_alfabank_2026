"""Порты источников: адаптеры к внешним мокам. Ошибки — `SourceNotFound` / `SourceUnavailable`
из домена."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.modules.enrichment.application.dto.accounting import AccountingReportsDTO
from src.modules.enrichment.application.dto.aml import (
    AmlSubjectDTO,
    LicenseDTO,
    ListScreeningDTO,
    PepScreeningDTO,
    ZskRiskDTO,
)
from src.modules.enrichment.application.dto.bank import BankStopListDTO, BankTurnoverDTO
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


class AmlListsSource(Protocol):
    """Перечни Росфинмониторинга: экстремизм и терроризм, решения МВК, ФРОМУ (115-ФЗ)."""

    async def screen(self, subjects: tuple[AmlSubjectDTO, ...]) -> ListScreeningDTO: ...


class PepSource(Protocol):
    """База публичных должностных лиц (ст. 7.3 115-ФЗ)."""

    async def screen(self, names: tuple[str, ...]) -> PepScreeningDTO: ...


class ZskSource(Protocol):
    """Платформа «Знай своего клиента» Банка России (ст. 7.6 115-ФЗ)."""

    async def fetch(self, inn: str) -> ZskRiskDTO: ...


class LicenseSource(Protocol):
    """Реестр лицензий: действующие лицензии компании (ст. 7 п. 15 115-ФЗ)."""

    async def fetch(self, inn: str) -> tuple[LicenseDTO, ...]: ...


class BankStopListSource(Protocol):
    """Внутренний стоп-лист банка (АБС): собственные данные банка, согласия не требуют."""

    async def fetch(self, inn: str) -> BankStopListDTO: ...


class BankTurnoverSource(Protocol):
    """Обороты по расчётному счёту в банке (АБС): собственные данные банка, согласия не
    требуют."""

    async def fetch(self, inn: str) -> BankTurnoverDTO: ...


@dataclass(frozen=True)
class Sources:
    registry: RegistrySource
    tax: TaxSource
    bureau: CreditBureauSource
    accounting: AccountingReportsSource
    counterparty: CounterpartyRiskSource
    person_bureau: PersonBureauSource
    aml_lists: AmlListsSource
    pep: PepSource
    zsk: ZskSource
    bank_stop_list: BankStopListSource
    bank_turnover: BankTurnoverSource
    licenses: LicenseSource
