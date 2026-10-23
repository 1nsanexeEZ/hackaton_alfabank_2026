"""Собственные данные банка (АБС): обороты по расчётному счёту и внутренний стоп-лист."""

# Без `from __future__ import annotations`: pydantic (ответы API на этих DTO) собирает схему по
# настоящим типам полей.
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TurnoverMonthDTO:
    month: str  # YYYY-MM
    inflow: Decimal  # поступления на счёт, рубли
    outflow: Decimal  # списания со счёта, рубли


@dataclass(frozen=True, slots=True)
class BankTurnoverDTO:
    """Клиент банка с какой даты и обороты по его счёту по месяцам, от старых к новым (без
    текущего месяца). Не клиент банка — `client_since = None`, оборотов нет."""

    client_since: date | None
    months: tuple[TurnoverMonthDTO, ...] = ()

    @property
    def annual_inflow(self) -> Decimal | None:
        """Поступления за последние 12 месяцев; меньше года оборотов — None."""
        if len(self.months) < 12:
            return None
        return sum((m.inflow for m in self.months[-12:]), Decimal(0))


@dataclass(frozen=True, slots=True)
class BankStopListDTO:
    """Компания во внутреннем стоп-листе банка или нет; причина — для банка, не для клиента."""

    listed: bool
    reason: str | None = None
    listed_at: date | None = None
