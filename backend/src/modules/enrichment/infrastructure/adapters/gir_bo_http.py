from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.modules.enrichment.application.dto.accounting import (
    AccountingPeriodDTO,
    AccountingReportsDTO,
)
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource

_THOUSAND = Decimal(1000)


class GirBoHttpSource(HttpSource):
    """ГИР БО: строки форм 0710001 / 0710002 в тыс. ₽ → периоды в рублях."""

    async def fetch(self, inn: str) -> AccountingReportsDTO:
        raw = await self._request("GET", f"/gir-bo/{inn}")
        try:
            return _map(raw)
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ ГИР БО: {exc}") from exc


def _rub(thousands: Any) -> Decimal:
    return Decimal(str(thousands)) * _THOUSAND


def _period(raw: dict[str, Any]) -> AccountingPeriodDTO:
    balance, income = raw["balance"], raw["income"]
    return AccountingPeriodDTO(
        year=int(raw["year"]),
        revenue=_rub(income["2110_revenue"]),
        cost_of_sales=_rub(income["2120_cost_of_sales"]),
        sales_profit=_rub(income["2200_sales_profit"]),
        interest_payable=_rub(income["2330_interest_payable"]),
        net_profit=_rub(income["2400_net_profit"]),
        fixed_assets=_rub(balance["1150_fixed_assets"]),
        inventories=_rub(balance["1210_inventories"]),
        receivables=_rub(balance["1230_receivables"]),
        cash=_rub(balance["1250_cash"]),
        equity=_rub(balance["1300_equity"]),
        total_assets=_rub(balance["1600_total_assets"]),
        long_term_liabilities=_rub(balance["1400_long_term_liabilities"]),
        short_term_liabilities=_rub(balance["1500_short_term_liabilities"]),
        total_liabilities=_rub(balance["1700_total_liabilities"]),
    )


def _map(raw: dict[str, Any]) -> AccountingReportsDTO:
    periods = sorted((_period(p) for p in raw.get("periods", [])), key=lambda p: p.year)
    return AccountingReportsDTO(
        available=bool(raw["available"]),
        reason=raw.get("reason"),
        periods=tuple(periods),
    )
