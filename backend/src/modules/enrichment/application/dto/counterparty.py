"""Контур.Фокус: суды, приставы, банкротство."""

# Без `from __future__ import annotations`: поле `date: date` в строковой аннотации
# указало бы само на себя, и pydantic (ответы API на этих DTO) не собрал бы схему.
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class ArbitrationDTO:
    as_defendant: int
    as_plaintiff: int
    defendant_sum: Decimal  # иски к компании, рубли


@dataclass(frozen=True, slots=True)
class EnforcementDTO:
    active: int
    sum: Decimal


@dataclass(frozen=True, slots=True)
class BankruptcyMessageDTO:
    date: date
    type: str
    case: str


@dataclass(frozen=True, slots=True)
class GovContractsDTO:
    count: int
    sum: Decimal


@dataclass(frozen=True, slots=True)
class CounterpartyRiskDTO:
    """Контур.Фокус: суды, приставы, банкротство."""

    reliability: Literal["green", "yellow", "red"]
    notes: tuple[str, ...]
    arbitration: ArbitrationDTO
    enforcement: EnforcementDTO
    bankruptcy_messages: tuple[BankruptcyMessageDTO, ...]
    gov_contracts: GovContractsDTO
    active_pledges: int
