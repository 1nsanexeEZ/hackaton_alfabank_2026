from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO, ObligationDTO
from src.modules.enrichment.application.interfaces.sources import CreditBureauSource
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource, kop_to_rub


class BkiHttpSource(HttpSource, CreditBureauSource):
    async def fetch(self, inn: str, consent_at: datetime) -> CreditHistoryDTO:
        raw = await self._request(
            "POST",
            "/bki/report",
            json={"inn": inn, "consent_at": consent_at.isoformat(), "request_id": str(uuid4())},
        )
        try:
            return map_credit_history(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable("bad_response", f"неожиданный ответ БКИ: {exc}") from exc


def map_credit_history(raw: dict[str, Any]) -> CreditHistoryDTO:
    """Отчёт БКИ: у компании и у физлица формат один."""
    obligations = tuple(
        ObligationDTO(
            creditor=str(o["creditor"]),
            kind=str(o["type"]),
            amount=kop_to_rub(o["amount_kop"]),
            balance=kop_to_rub(o["outstanding_kop"]),
            monthly_payment=kop_to_rub(o["monthly_payment_kop"]),
            opened_at=date.fromisoformat(o["opened"]),
            closes_at=date.fromisoformat(o["closes"]) if o.get("closes") else None,
            overdue_days=int(o["overdue_days"]),
        )
        for o in raw["obligations"]
    )
    max_overdue = max((int(o["max_overdue_days"]) for o in raw["obligations"]), default=0)
    total_monthly = sum(
        (kop_to_rub(o["monthly_payment_kop"]) for o in raw["obligations"]), Decimal(0)
    )
    has_overdue = any(int(o["overdue_days"]) > 0 for o in raw["obligations"])
    return CreditHistoryDTO(
        obligations=obligations,
        inquiries_last_30d=int(raw["inquiries_30d"]),
        has_active_overdue=has_overdue,
        max_overdue_days_12m=max_overdue,
        total_monthly_payments=total_monthly,
    )
