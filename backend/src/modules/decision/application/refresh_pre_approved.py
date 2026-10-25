"""Use case RefreshExpiringPreApproved: ночной пакет предодобрения.

Предложение действует 30 дней. Чтобы оно не пропадало молча до следующего события clients, пакет
пересчитывает компании, у которых предложения истекают в ближайшие `within_days` дней (и уже
истекшие — если пакет какое-то время не работал). Каждая компания — в своей транзакции тем же
RecalculatePreApproved, что и по событиям: сверка с ЕГРЮЛ, оценка, политика,
`PreApprovedOffersUpdated`. Ошибка одной компании не останавливает остальные: её предложения не
продлены, и следующий проход возьмёт её снова. Политика — активная на начало прохода: админ мог
сменить её с прошлой ночи.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from src.core.domain.clock import Clock
from src.modules.decision.application.policy_versions import PolicyProvider
from src.modules.decision.application.ports import PreApprovalTransactions
from src.modules.decision.application.pre_approval import RecalculatePreApprovedUseCase

logger = logging.getLogger(__name__)


class RefreshExpiringPreApprovedUseCase:
    def __init__(
        self,
        transactions: PreApprovalTransactions,
        policies: PolicyProvider,
        clock: Clock,
        key_rate: Decimal,
    ) -> None:
        self._transactions = transactions
        self._policies = policies
        self._clock = clock
        self._key_rate = key_rate

    async def execute(self, within_days: int, batch_size: int = 500) -> int:
        """Сколько компаний пересчитано."""
        horizon = (self._clock.now() + timedelta(days=within_days)).date()
        async with self._transactions() as transaction:
            due = await transaction.offers.organizations_expiring_by(horizon, batch_size)
            policy = await self._policies.active(transaction.policy_versions)
        refreshed = 0
        for organization_id in due:
            try:
                async with self._transactions() as transaction:
                    await RecalculatePreApprovedUseCase(
                        transaction.offers,
                        policy,
                        transaction.clients,
                        transaction.products,
                        transaction.scoring,
                        self._clock,
                        self._key_rate,
                    ).execute(organization_id, outbox=transaction.outbox)
                    await transaction.commit()
            except Exception:
                logger.exception("Pre-approval refresh failed for organization %s", organization_id)
                continue
            refreshed += 1
        return refreshed
