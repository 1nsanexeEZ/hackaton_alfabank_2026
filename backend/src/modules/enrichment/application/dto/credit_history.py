"""БКИ: кредитная история компании или физлица и запрос по физлицу."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ObligationDTO:
    creditor: str
    kind: str
    amount: Decimal
    balance: Decimal
    monthly_payment: Decimal
    opened_at: date
    closes_at: date | None
    overdue_days: int


@dataclass(frozen=True, slots=True)
class CreditHistoryDTO:
    obligations: tuple[ObligationDTO, ...]
    inquiries_last_30d: int
    has_active_overdue: bool
    max_overdue_days_12m: int
    total_monthly_payments: Decimal


@dataclass(frozen=True, slots=True)
class PersonDTO:
    """A person whose own credit history is asked; `company_inn` — the company
    on whose behalf the bank asks."""

    last_name: str
    first_name: str
    middle_name: str | None
    company_inn: str
