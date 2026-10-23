"""ГИР БО: бухотчётность юрлица."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AccountingPeriodDTO:
    """Год бухотчётности из ГИР БО, рубли (у источника — тыс. ₽)."""

    year: int
    revenue: Decimal
    cost_of_sales: Decimal
    sales_profit: Decimal
    interest_payable: Decimal
    net_profit: Decimal
    fixed_assets: Decimal
    inventories: Decimal
    receivables: Decimal
    cash: Decimal
    equity: Decimal
    total_assets: Decimal
    long_term_liabilities: Decimal
    short_term_liabilities: Decimal
    total_liabilities: Decimal  # строка 1700 — итог пассива


@dataclass(frozen=True, slots=True)
class AccountingReportsDTO:
    available: bool
    reason: str | None  # почему отчётности нет: ИП, компания младше года
    periods: tuple[AccountingPeriodDTO, ...]  # от старых к новым

    @property
    def latest(self) -> AccountingPeriodDTO | None:
        return max(self.periods, key=lambda p: p.year) if self.periods else None
