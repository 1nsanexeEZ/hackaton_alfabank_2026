from __future__ import annotations

from datetime import date
from typing import Any

from src.modules.enrichment.application.dto.tax import AccountBlockDTO, TaxProfileDTO
from src.modules.enrichment.application.interfaces.sources import TaxSource
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource, kop_to_rub


class FnsHttpSource(HttpSource, TaxSource):
    async def fetch(self, inn: str) -> TaxProfileDTO:
        raw = await self._request("GET", f"/fns/{inn}")
        try:
            return _map(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ ФНС: {exc}") from exc


def _map(raw: dict[str, Any]) -> TaxProfileDTO:
    revenue = raw.get("revenue_kop")
    expenses = raw.get("expenses_kop")
    return TaxProfileDTO(
        tax_arrears=kop_to_rub(raw["arrears_kop"]),
        avg_headcount=int(raw["avg_headcount"]),
        reported_revenue=kop_to_rub(revenue) if revenue is not None else None,
        reported_expenses=kop_to_rub(expenses) if expenses is not None else None,
        report_year=raw.get("report_year"),
        tax_regime=str(raw["tax_regime"]),
        disqualified_head=bool(raw["disqualified_head"]),
        in_msp_registry=bool(raw["msp_registry"]),
        # Нет поля в ответе — блокировок нет.
        account_blocks=tuple(
            AccountBlockDTO(
                decision_number=str(block["decision_number"]),
                date=date.fromisoformat(block["date"]),
                authority_code=str(block["authority_code"]),
                reason=str(block["reason"]),
            )
            for block in raw.get("account_blocks", [])
        ),
        mass_head=bool(raw["mass_head"]) if "mass_head" in raw else None,
    )
