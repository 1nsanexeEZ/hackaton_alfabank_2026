"""Use case FounderPrescreen: «личный скоринг учредителя (предскрин) → прошёл?» ветки стартапа.

У стартапа нет оборотов и отчётности, поэтому до заявки на STARTUP банк смотрит личную
кредитную историю учредителя:
1. учредитель — участник компании, чьё ФИО совпало с руководителем по реестру
   (`clients.get_registry_head`); нет такого — 422 `founder_not_found`;
2. нужно его действующее согласие на запрос своей кредитной истории
   (`identity`, `credit_bureau_personal`); нет — 422 `consent_required`;
3. запрос в БКИ физлица сразу, без заявки (`enrichment.lookup_person_bureau`), оценка —
   `scoring.prescreen_person`;
4. результат хранится и действует 30 дней, как предодобрение. `failed` — это «отказ (стартап)»
   на схеме: клиент видит причины. Политика не пускает заявку на STARTUP без пройденного
   предскрина (policy_v4, `STOP_FOUNDER_PRESCREEN`).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ValidationError
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.application.ports import (
    FounderPrescreen,
    FounderPrescreenRepository,
    PrescreenCheck,
)
from src.modules.enrichment.facade import EnrichmentFacade, PersonDTO
from src.modules.identity.facade import IdentityFacade
from src.modules.scoring.facade import ScoringFacade

PRESCREEN_VALID_DAYS = 30


class FounderPrescreenUseCase:
    def __init__(
        self,
        repository: FounderPrescreenRepository,
        clients: ClientsFacade,
        identity: IdentityFacade,
        enrichment: EnrichmentFacade,
        scoring: ScoringFacade,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._clients = clients
        self._identity = identity
        self._enrichment = enrichment
        self._scoring = scoring
        self._clock = clock

    async def run(self, organization_id: UUID) -> FounderPrescreen:
        founder_id = await self._clients.get_registry_head(organization_id)
        account = await self._identity.get_account(founder_id) if founder_id else None
        if founder_id is None or account is None:
            raise ValidationError(
                "Учредитель по реестру не найден среди участников компании",
                details={"code": "founder_not_found"},
            )
        consent = await self._identity.get_active_consent(founder_id, "credit_bureau_personal")
        if consent is None:
            raise ValidationError(
                "Нужно согласие учредителя на запрос его кредитной истории",
                details={"code": "consent_required", "consent": "credit_bureau_personal"},
            )
        company = await self._clients.get_snapshot(organization_id)
        history = await self._enrichment.lookup_person_bureau(
            PersonDTO(account.last_name, account.first_name, account.middle_name, company.inn),
            consent.given_at,
        )
        checked = self._scoring.prescreen_person(history)
        now = self._clock.now()
        prescreen = FounderPrescreen(
            id=uuid4(),
            organization_id=organization_id,
            founder_account_id=founder_id,
            founder_name=" ".join(
                p for p in (account.last_name, account.first_name, account.middle_name) if p
            ),
            status="passed" if checked.passed else "failed",
            reasons=tuple(PrescreenCheck(r.code, r.passed, r.message) for r in checked.reasons),
            version=checked.version,
            checked_at=now,
            valid_until=now + timedelta(days=PRESCREEN_VALID_DAYS),
        )
        await self._repository.add(prescreen)
        return prescreen
