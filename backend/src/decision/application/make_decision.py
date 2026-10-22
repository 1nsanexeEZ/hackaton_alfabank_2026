"""Use case MakeDecision: по команде процесса собрать вход из соседей, применить кредитную
политику, посчитать платёж оффера, сохранить решение и ответить `DecisionMade`.

- идемпотентность по event_id команды: повтор возвращает то же решение и повторно публикует
  ответ (causation_id = event_id команды);
- вход собирает `DecisionInputBuilder` (заявка, снимок обогащения, скоринг, продукты); нет
  скоринга или снимка — это данные для политики (решит андеррайтер), а не ошибка;
- платёж оффера считает `products.calculate_payment` — одна формула на всю систему;
- оффер действует `offer_valid_days` дней (7 по политике v1).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.messaging.contracts.decision import MakeDecision
from src.core.messaging.outbox import OutboxWriter
from src.decision.application.input_builder import DecisionInputBuilder
from src.decision.application.ports import DecisionRepository
from src.decision.application.replies import offer_schedule, publish_decision
from src.decision.domain.model import PolicyDecision
from src.decision.domain.policy import CreditPolicy
from src.decision.domain.result import automatic_result
from src.products.facade import ProductsFacade


class MakeDecisionUseCase:
    def __init__(
        self,
        repository: DecisionRepository,
        policy: CreditPolicy,
        builder: DecisionInputBuilder,
        products: ProductsFacade,
        clock: Clock,
        key_rate: Decimal,
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._builder = builder
        self._products = products
        self._clock = clock
        self._key_rate = key_rate

    async def execute(
        self, command: MakeDecision, *, command_event_id: UUID, outbox: OutboxWriter
    ) -> None:
        existing = await self._repository.get_by_command(command_event_id)
        if existing is not None:
            await publish_decision(outbox, existing, command_event_id)
            return

        collected = await self._builder.collect(command.application_id)
        decision = _with_offer_schedule(
            self._policy.decide(collected.decision_input, key_rate=self._key_rate)
        )
        monthly_payment = None
        if decision.terms is not None:
            terms = decision.terms
            schedule = self._products.calculate_payment(
                terms.amount, terms.term_months, terms.rate, offer_schedule(terms.schedule_type)
            )
            monthly_payment = schedule.monthly_payment

        result = automatic_result(
            decision,
            result_id=uuid4(),
            application_id=command.application_id,
            command_event_id=command_event_id,
            inputs=collected.refs,
            monthly_payment=monthly_payment,
            offer_valid_days=self._policy.config.offer_valid_days,
            now=self._clock.now(),
        )
        await self._repository.add(result)
        await publish_decision(outbox, result, command_event_id)


def _with_offer_schedule(decision: PolicyDecision) -> PolicyDecision:
    """График оффера — из тех, что понимает контракт `DecisionMade` и записанное решение."""
    terms = decision.terms
    if terms is None or offer_schedule(terms.schedule_type) == terms.schedule_type:
        return decision
    return replace(decision, terms=replace(terms, schedule_type="annuity"))
