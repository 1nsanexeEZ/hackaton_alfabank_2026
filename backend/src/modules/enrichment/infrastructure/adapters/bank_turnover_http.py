from __future__ import annotations

from datetime import date
from typing import Any

from src.modules.enrichment.application.dto.bank import BankTurnoverDTO, TurnoverMonthDTO
from src.modules.enrichment.application.interfaces.sources import BankTurnoverSource
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource, kop_to_rub


class BankTurnoverHttpSource(HttpSource, BankTurnoverSource):
    """Обороты по расчётному счёту в АБС (мок external-mocks), суммы у источника — в копейках.
    Боевая АБС — другой адаптер за тем же портом `BankTurnoverSource`."""

    async def fetch(self, inn: str) -> BankTurnoverDTO:
        raw = await self._request("GET", f"/abs/accounts/{inn}")
        try:
            return _map(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ АБС: {exc}") from exc


def _map(raw: dict[str, Any]) -> BankTurnoverDTO:
    since = raw.get("client_since")
    months = tuple(
        TurnoverMonthDTO(
            month=str(item["month"]),
            inflow=kop_to_rub(item["credit_kop"]),
            outflow=kop_to_rub(item["debit_kop"]),
        )
        for item in raw.get("turnover", [])
    )
    if [m.month for m in months] != sorted(m.month for m in months):
        raise ValueError("месяцы оборотов не по порядку")
    return BankTurnoverDTO(client_since=date.fromisoformat(since) if since else None, months=months)
