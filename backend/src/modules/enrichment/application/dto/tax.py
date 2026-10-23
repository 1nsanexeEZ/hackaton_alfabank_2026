"""ФНС «Прозрачный бизнес»: налоговый профиль."""

# Без `from __future__ import annotations`: поле `date: date` в строковой аннотации
# указало бы само на себя, и pydantic (ответы API на этих DTO) не собрал бы схему.
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AccountBlockDTO:
    """Решение ФНС о приостановлении операций по счетам."""

    decision_number: str
    date: date
    authority_code: str
    reason: str


@dataclass(frozen=True, slots=True)
class TaxProfileDTO:
    tax_arrears: Decimal
    avg_headcount: int
    reported_revenue: Decimal | None
    reported_expenses: Decimal | None
    report_year: int | None
    tax_regime: str
    disqualified_head: bool
    in_msp_registry: bool
    account_blocks: tuple[AccountBlockDTO, ...] = ()
