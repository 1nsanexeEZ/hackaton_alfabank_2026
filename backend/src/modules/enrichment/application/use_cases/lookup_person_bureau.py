"""Кредитная история физлица сразу, без заявки (предскрин учредителя)."""

from __future__ import annotations

from datetime import datetime

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO, PersonDTO
from src.modules.enrichment.application.interfaces.sources import PersonBureauSource
from src.modules.enrichment.domain.exceptions import SourceNotFound, SourceUnavailable


class LookupPersonBureauUseCase:
    def __init__(self, person_bureau: PersonBureauSource) -> None:
        self._person_bureau = person_bureau

    async def execute(self, person: PersonDTO, consent_at: datetime) -> CreditHistoryDTO | None:
        """Без кеша: согласие и ответ бюро — на момент запроса. None — бюро не знает человека;
        InfrastructureError — оно не ответило."""
        try:
            return await self._person_bureau.fetch(person, consent_at)
        except SourceNotFound:
            return None
        except SourceUnavailable as exc:
            raise InfrastructureError("Бюро кредитных историй временно недоступно") from exc
