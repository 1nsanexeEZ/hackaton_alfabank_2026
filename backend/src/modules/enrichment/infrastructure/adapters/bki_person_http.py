from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO, PersonDTO
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.bki_http import map_credit_history
from src.modules.enrichment.infrastructure.adapters.http_base import HttpSource


class BkiPersonHttpSource(HttpSource):
    """Кредитный отчёт физлица (руководителя): в запрос уходит согласие самого человека."""

    async def fetch(self, person: PersonDTO, consent_at: datetime) -> CreditHistoryDTO:
        raw = await self._request(
            "POST",
            "/bki/person-report",
            json={
                "last_name": person.last_name,
                "first_name": person.first_name,
                "middle_name": person.middle_name,
                "company_inn": person.company_inn,
                "consent_at": consent_at.isoformat(),
                "request_id": str(uuid4()),
            },
        )
        try:
            return map_credit_history(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceUnavailable(
                "bad_response", f"неожиданный ответ БКИ по физлицу: {exc}"
            ) from exc
