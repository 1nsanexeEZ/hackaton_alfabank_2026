"""Use case RecordManualDecision: решение андеррайтера по задаче процесса.

Проверки (нарушение → `ManualDecisionRejected`, процесс вернёт задачу андеррайтеру):
- комментарий обязателен — это аудит;
- одобрение и встречное предложение — с условиями, дозапрос — с документами или полями,
  отправить заявку снова на ручную проверку нельзя;
- сумма, срок и ставка — в рамках продукта из заявки (андеррайтер не выдаст больше продукта);
- полномочия: сумма не больше лимита роли (`underwriter` — 50 млн), выше — кредитный комитет.

Успех → новое решение `decided_by=underwriter` с `override_of` = последнее авторешение по заявке
(оно не удаляется) → `DecisionMade`. Повтор команды с тем же event_id — тот же ответ.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.messaging.contracts.decision import ManualDecisionRejected, RecordManualDecision
from src.core.messaging.outbox import OutboxWriter
from src.modules.applications.facade import ApplicationsFacade
from src.modules.decision.application.ports import DecisionRepository
from src.modules.decision.application.replies import offer_schedule, publish_decision
from src.modules.decision.domain.explanations import rub
from src.modules.decision.domain.model import InfoNeed, Limits, RuleHit
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.domain.result import ApprovedTerms, DecisionInputRefs, DecisionResult
from src.modules.products.facade import ProductsFacade, ProductTermsDTO

UNDERWRITER_AUTHORITY = Decimal(50_000_000)

# Клиенту — нейтральный текст исхода; комментарий андеррайтера внутренний (аудит).
MANUAL_EXPLANATIONS = {
    "APPROVE": "Специалист банка рассмотрел заявку и одобрил кредит.",
    "COUNTER_OFFER": "Специалист банка рассмотрел заявку и подготовил встречное предложение.",
    "REQUEST_INFO": "Специалист банка рассмотрел заявку: для решения нужно немного больше "
    "информации.",
    "REJECT": "Специалист банка рассмотрел заявку. К сожалению, сейчас мы не можем одобрить "
    "кредит.",
}
_WITH_TERMS = frozenset({"APPROVE", "COUNTER_OFFER"})
# Подсказки авторешения остаются полезны клиенту при отказе и встречном предложении.
_KEEP_HINTS = frozenset({"COUNTER_OFFER", "REJECT"})


class ManualDecisionError(Exception):
    """Ручное решение нарушает правила; текст — для андеррайтера."""


@dataclass(frozen=True, slots=True)
class _Checked:
    terms: ApprovedTerms | None
    requested_info: InfoNeed | None
    trace: tuple[RuleHit, ...]


class RecordManualDecisionUseCase:
    def __init__(
        self,
        repository: DecisionRepository,
        policy: CreditPolicy,
        applications: ApplicationsFacade,
        products: ProductsFacade,
        clock: Clock,
        key_rate: Decimal,
        authority_limit: Decimal = UNDERWRITER_AUTHORITY,
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._applications = applications
        self._products = products
        self._clock = clock
        self._key_rate = key_rate
        self._authority = authority_limit

    async def execute(
        self, command: RecordManualDecision, *, command_event_id: UUID, outbox: OutboxWriter
    ) -> None:
        existing = await self._repository.get_by_command(command_event_id)
        if existing is not None:
            await publish_decision(outbox, existing, command_event_id)
            return

        source = await self._applications.get_scoring_input(command.application_id)
        now = self._clock.now()
        try:
            checked = self._check(command, source.product_terms, now)
        except ManualDecisionError as error:
            await outbox.add(
                ManualDecisionRejected(
                    application_id=command.application_id,
                    task_id=command.task_id,
                    reason=str(error),
                ),
                key=command.application_id,
                correlation_id=command.application_id,
                causation_id=command_event_id,
            )
            return

        auto = await self._repository.latest_automatic(command.application_id)
        result = DecisionResult(
            id=uuid4(),
            application_id=command.application_id,
            requested_by_command=command_event_id,
            policy_version=auto.policy_version if auto is not None else self._policy.version,
            key_rate=auto.key_rate if auto is not None else self._key_rate,
            inputs=auto.inputs
            if auto is not None
            else DecisionInputRefs(
                scoring_result_id=None,
                enrichment_snapshot_id=None,
                product_code=source.product_terms.code,
                product_version=source.product_terms.version,
            ),
            outcome=command.outcome,
            terms=checked.terms,
            alternative_product_code=None,
            reason_codes=(),
            client_explanation=_explanation(command.outcome, checked.requested_info),
            improvement_hints=auto.improvement_hints
            if auto is not None and command.outcome in _KEEP_HINTS
            else (),
            requested_info=checked.requested_info,
            rule_trace=checked.trace,
            limits=auto.limits if auto is not None else Limits(),
            decided_by_type="underwriter",
            decided_by_id=command.underwriter_id,
            override_of=auto.id if auto is not None else None,
            comment=command.comment.strip(),
            decided_at=now,
        )
        await self._repository.add(result)
        await publish_decision(outbox, result, command_event_id)

    def _check(
        self, command: RecordManualDecision, product: ProductTermsDTO, now: datetime
    ) -> _Checked:
        if not command.comment.strip():
            raise ManualDecisionError("Комментарий к ручному решению обязателен")
        trace = [RuleHit("manual.comment", True, "комментарий андеррайтера есть")]
        if command.outcome == "MANUAL_REVIEW":
            raise ManualDecisionError(
                "Ручное решение не может снова отправить заявку на ручную проверку"
            )

        requested_info = None
        if command.outcome == "REQUEST_INFO":
            info = command.requested_info
            if info is None or not (info.fields or info.documents):
                raise ManualDecisionError("Для дозапроса укажите, какие документы или данные нужны")
            requested_info = InfoNeed(tuple(info.fields), tuple(info.documents), info.comment)

        terms = None
        if command.outcome in _WITH_TERMS:
            if command.terms is None:
                raise ManualDecisionError("Для одобрения укажите сумму, срок и ставку")
            manual = command.terms
            _within("Сумма", manual.amount, product.amount_min, product.amount_max, rub)
            _within(
                "Срок",
                Decimal(manual.term_months),
                Decimal(product.term_min_months),
                Decimal(product.term_max_months),
                lambda value: f"{value} мес.",
            )
            _within("Ставка", manual.rate, product.rate_base, product.rate_max, lambda v: f"{v}%")
            trace.append(
                RuleHit(
                    "manual.product_bounds",
                    True,
                    f"{rub(manual.amount)} на {manual.term_months} мес. под {manual.rate}% — "
                    f"в рамках продукта {product.code}",
                )
            )
            if manual.amount > self._authority:
                raise ManualDecisionError(
                    f"Сумма {rub(manual.amount)} больше полномочий андеррайтера "
                    f"({rub(self._authority)}) — нужно решение кредитного комитета"
                )
            trace.append(
                RuleHit(
                    "manual.authority",
                    True,
                    f"сумма в пределах полномочий андеррайтера {rub(self._authority)}",
                )
            )
            schedule_type = offer_schedule(
                product.repayment_options[0] if product.repayment_options else "annuity"
            )
            payment = self._products.calculate_payment(
                manual.amount, manual.term_months, manual.rate, schedule_type
            )
            terms = ApprovedTerms(
                amount=manual.amount,
                term_months=manual.term_months,
                rate=manual.rate,
                schedule_type=schedule_type,
                monthly_payment=payment.monthly_payment,
                conditions=tuple(manual.conditions),
                expires_at=now + timedelta(days=self._policy.config.offer_valid_days),
            )
        return _Checked(terms, requested_info, tuple(trace))


def _within(
    title: str, value: Decimal, low: Decimal, high: Decimal, show: Callable[[Decimal], str]
) -> None:
    if not low <= value <= high:
        raise ManualDecisionError(
            f"{title} {show(value)} вне рамок продукта: от {show(low)} до {show(high)}"
        )


def _explanation(outcome: str, requested_info: InfoNeed | None) -> str:
    text = MANUAL_EXPLANATIONS[outcome]
    if requested_info is not None and requested_info.comment:
        return f"{text} {requested_info.comment}"
    return text
