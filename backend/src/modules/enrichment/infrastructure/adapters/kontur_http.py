from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.modules.enrichment.application.dto.counterparty import (
    ArbitrationDTO,
    BankruptcyMessageDTO,
    CounterpartyRiskDTO,
    EnforcementDTO,
    GovContractsDTO,
)
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource

_RELIABILITY = frozenset({"green", "yellow", "red"})


class KonturHttpSource(HttpSource):
    """Контур.Фокус: арбитраж, ФССП, банкротство; суммы у источника — в рублях."""

    async def fetch(self, inn: str) -> CounterpartyRiskDTO:
        raw = await self._request("GET", f"/kontur/{inn}")
        try:
            return _map(raw)
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ Контура: {exc}") from exc


def _rub(value: Any) -> Decimal:
    return Decimal(str(value))


def _map(raw: dict[str, Any]) -> CounterpartyRiskDTO:
    reliability = str(raw["reliability"])
    if reliability not in _RELIABILITY:
        raise ValueError(f"неизвестная надёжность {reliability!r}")
    arbitration = raw["arbitration"]
    enforcement = raw["enforcement_proceedings"]
    contracts = raw.get("gov_contracts") or {"count": 0, "sum_rub": 0}
    return CounterpartyRiskDTO(
        reliability=reliability,  # type: ignore[arg-type]
        notes=tuple(str(note) for note in raw.get("reliability_notes", [])),
        arbitration=ArbitrationDTO(
            as_defendant=int(arbitration["as_defendant"]),
            as_plaintiff=int(arbitration["as_plaintiff"]),
            defendant_sum=_rub(arbitration["defendant_sum_rub"]),
        ),
        enforcement=EnforcementDTO(
            active=int(enforcement["active"]), sum=_rub(enforcement["sum_rub"])
        ),
        bankruptcy_messages=tuple(
            BankruptcyMessageDTO(
                date=date.fromisoformat(message["date"]),
                type=str(message["type"]),
                case=str(message["case"]),
            )
            for message in raw.get("bankruptcy_messages", [])
        ),
        gov_contracts=GovContractsDTO(
            count=int(contracts["count"]), sum=_rub(contracts["sum_rub"])
        ),
        active_pledges=int(raw.get("active_pledges", 0)),
    )
