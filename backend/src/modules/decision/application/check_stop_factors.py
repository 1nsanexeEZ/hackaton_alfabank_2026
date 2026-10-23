"""Use case CheckStopFactors: стоп-факторы до скоринга, как на общей схеме («Запросы» →
«Стоп-фактор?» → модель).

- вход тот же, что у решения (`DecisionInputBuilder`), но без результата скоринга: стоп-факторам
  модель не нужна, а результат прошлой итерации (после дозапроса) к этой проверке не относится;
- ни один не сработал → `StopFactorsPassed`, процесс идёт к скорингу; ничего не сохраняется;
- сработал → решение сохраняется как обычное автоматическое (трасса правил, версия политики) и
  уходит обычным `DecisionMade`: процесс, заявка и уведомления обрабатывают его как любое решение;
- идемпотентность по event_id команды: повтор возвращает то же решение.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.messaging.contracts.decision import CheckStopFactors, StopFactorsPassed
from src.core.messaging.outbox import OutboxWriter
from src.modules.decision.application.input_builder import DecisionInputBuilder
from src.modules.decision.application.ports import DecisionRepository
from src.modules.decision.application.replies import publish_decision
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.domain.result import automatic_result


class CheckStopFactorsUseCase:
    def __init__(
        self,
        repository: DecisionRepository,
        policy: CreditPolicy,
        builder: DecisionInputBuilder,
        clock: Clock,
        key_rate: Decimal,
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._builder = builder
        self._clock = clock
        self._key_rate = key_rate

    async def execute(
        self, command: CheckStopFactors, *, command_event_id: UUID, outbox: OutboxWriter
    ) -> None:
        existing = await self._repository.get_by_command(command_event_id)
        if existing is not None:
            await publish_decision(outbox, existing, command_event_id)
            return

        collected = await self._builder.collect(command.application_id)
        decision = self._policy.screen(collected.decision_input, key_rate=self._key_rate)
        if decision is None:
            await outbox.add(
                StopFactorsPassed(application_id=command.application_id),
                key=command.application_id,
                correlation_id=command.application_id,
                causation_id=command_event_id,
            )
            return

        result = automatic_result(
            decision,
            result_id=uuid4(),
            application_id=command.application_id,
            command_event_id=command_event_id,
            inputs=replace(collected.refs, scoring_result_id=None),
            monthly_payment=None,
            offer_valid_days=self._policy.config.offer_valid_days,
            now=self._clock.now(),
        )
        await self._repository.add(result)
        await publish_decision(outbox, result, command_event_id)
