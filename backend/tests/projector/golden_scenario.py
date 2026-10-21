"""Four applications of two demo companies over two days, as the neighbours
would publish them. Each step first changes the state of the neighbours (what
their facades return from now on), then publishes its events.

- A1 Ромашка, UNSECURED 3 млн: auto approval, offer accepted, signing;
- A2 Ромашка, CREDIT_LINE 12 млн: manual review (cash gap), counter offer by the underwriter;
- A3 ИП Иванов, OVERDRAFT 1 млн: manual review, the task is still open;
- A4 ИП Иванов, UNSECURED 2 млн: auto rejection;
- plus a new member of Ромашка and pre-approved offers of ИП Иванов.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from src.core.messaging.contracts.applications import (
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferTerms,
)
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.clients import MemberAdded
from src.core.messaging.contracts.decision import DecisionMade, PreApprovedOffersUpdated
from src.core.messaging.contracts.process import (
    ProcessCompleted,
    ProcessStarted,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from tests.projector.world import (
    World,
    decision,
    envelope,
    offer,
    pre_approved,
    scoring_result,
    task,
    uid,
)

DAY1 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
DAY2 = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)

ROMASHKA, IVANOV = uid("org-romashka"), uid("org-ivanov")
A1, A2, A3, A4 = (uid(f"application-{n}") for n in range(1, 5))
P1, P2, P3, P4 = (uid(f"process-{n}") for n in range(1, 5))
T2, T3 = uid("task-2"), uid("task-3")
UNDERWRITER, ACCOUNTANT = uid("underwriter"), uid("accountant")
STAGE = "Проверяем данные о компании"


@dataclass(frozen=True)
class Step:
    at: datetime
    messages: tuple[IntegrationMessage, ...]
    change: Callable[[World], Any] | None = None


def at(base: datetime, minutes: float) -> datetime:
    return base + timedelta(minutes=minutes)


def submitted(app: Any, org: Any, product: str, amount: str, term: int) -> ApplicationSubmitted:
    return ApplicationSubmitted(
        application_id=app,
        organization_id=org,
        product_code=product,
        amount=Decimal(amount),
        term_months=term,
        purpose="working_capital",
    )


def moved(app: Any, org: Any, source: str, target: str, stage: str | None = None) -> Any:
    return ApplicationStatusChanged(
        application_id=app,
        organization_id=org,
        from_status=source,
        to_status=target,
        client_stage=stage,
    )


def terms(kind: str, amount: str, rate: str, expires_at: datetime) -> OfferTerms:
    return OfferTerms(
        kind=kind,  # type: ignore[arg-type]
        amount=Decimal(amount),
        term_months=24,
        rate=Decimal(rate),
        monthly_payment=Decimal("158613.29"),
        expires_at=expires_at,
    )


def card(app: Any, org: Any, **values: Any) -> Callable[[World], Any]:
    def change(world: World) -> Any:
        if app in world.applications.cards:
            return world.update_card(app, **values)
        return world.card(app, org, **values)

    return change


def steps() -> list[Step]:
    expires = DAY1 + timedelta(days=30)
    a1 = dict(company="romashka", number="КР-2026-000101", product_code="UNSECURED")
    a2 = dict(
        company="romashka",
        number="КР-2026-000102",
        product_code="CREDIT_LINE",
        amount=Decimal("12000000"),
    )
    a3 = dict(
        company="ivanov",
        number="КР-2026-000103",
        product_code="OVERDRAFT",
        amount=Decimal("1000000"),
        term_months=12,
    )
    a4 = dict(
        company="ivanov",
        number="КР-2026-000104",
        product_code="UNSECURED",
        amount=Decimal("2000000"),
        term_months=36,
    )
    d1, d2a, d2b, d3, d4 = (uid(f"decision-{n}") for n in ("1", "2a", "2b", "3", "4"))

    def both(*changes: Callable[[World], Any]) -> Callable[[World], None]:
        def change(world: World) -> None:
            for one in changes:
                one(world)

        return change

    return [
        # --- A1: auto approval -------------------------------------------------
        Step(
            DAY1,
            (
                submitted(A1, ROMASHKA, "UNSECURED", "3000000", 24),
                moved(A1, ROMASHKA, "draft", "submitted"),
            ),
            card(A1, ROMASHKA, **a1, updated_at=DAY1, submitted_at=DAY1),
        ),
        Step(
            at(DAY1, 1),
            (ProcessStarted(process_id=P1, application_id=A1, workflow_code="express_v1"),),
        ),
        Step(
            at(DAY1, 2),
            (moved(A1, ROMASHKA, "submitted", "in_review", STAGE),),
            card(
                A1,
                ROMASHKA,
                status="in_review",
                version=3,
                updated_at=at(DAY1, 2),
                client_stage=STAGE,
            ),
        ),
        Step(
            at(DAY1, 3),
            (
                StepCompleted(
                    process_id=P1,
                    application_id=A1,
                    node_id="fetch",
                    step_code="fetch_enrichment",
                    client_stage=STAGE,
                ),
            ),
        ),
        Step(
            at(DAY1, 5),
            (
                StepCompleted(
                    process_id=P1, application_id=A1, node_id="score", step_code="calculate_score"
                ),
            ),
            lambda w: w.scoring.add_result(scoring_result(A1, 780, "B")),
        ),
        Step(
            at(DAY1, 10),
            (
                DecisionMade(
                    application_id=A1,
                    decision_id=d1,
                    outcome="APPROVE",
                    offer=terms("as_requested", "3000000", "23.5", expires),
                    decided_by="auto",
                    client_explanation="Кредит одобрен на запрошенных условиях",
                ),
            ),
            lambda w: w.decision.add_decision(
                decision(A1, "APPROVE", decided_at=at(DAY1, 10), decision_id=d1)
            ),
        ),
        Step(
            at(DAY1, 11),
            (moved(A1, ROMASHKA, "in_review", "offer_ready", STAGE),),
            card(
                A1,
                ROMASHKA,
                status="offer_ready",
                version=4,
                updated_at=at(DAY1, 11),
                offer=offer("3000000", "23.5", d1, expires),
            ),
        ),
        Step(
            at(DAY1, 30),
            (
                OfferAccepted(application_id=A1, organization_id=ROMASHKA),
                moved(A1, ROMASHKA, "offer_ready", "signing", STAGE),
            ),
            card(A1, ROMASHKA, status="signing", version=5, updated_at=at(DAY1, 30)),
        ),
        # --- A2: manual review, counter offer ----------------------------------
        Step(
            at(DAY1, 60),
            (
                submitted(A2, ROMASHKA, "CREDIT_LINE", "12000000", 24),
                moved(A2, ROMASHKA, "draft", "submitted"),
            ),
            card(A2, ROMASHKA, **a2, updated_at=at(DAY1, 60), submitted_at=at(DAY1, 60)),
        ),
        Step(
            at(DAY1, 62),
            (moved(A2, ROMASHKA, "submitted", "in_review"),),
            card(A2, ROMASHKA, status="in_review", version=3, updated_at=at(DAY1, 62)),
        ),
        Step(
            at(DAY1, 70),
            (
                DecisionMade(
                    application_id=A2,
                    decision_id=d2a,
                    outcome="MANUAL_REVIEW",
                    decided_by="auto",
                    client_explanation="Заявку проверит специалист банка",
                ),
            ),
            both(
                lambda w: w.scoring.add_result(
                    scoring_result(A2, 610, "C", ("cash_gap_forecast",))
                ),
                lambda w: w.decision.add_decision(
                    decision(
                        A2,
                        "MANUAL_REVIEW",
                        decided_at=at(DAY1, 70),
                        decision_id=d2a,
                        reason_codes=("AMOUNT_ABOVE_AUTO_LIMIT", "CASH_GAP_FORECAST"),
                    )
                ),
            ),
        ),
        Step(
            at(DAY1, 71),
            (
                UserTaskCreated(
                    task_id=T2,
                    process_id=P2,
                    application_id=A2,
                    task_type="manual_review",
                    candidate_role="underwriter",
                    due_at=at(DAY1, 71 + 24 * 60),
                ),
            ),
            lambda w: w.process.add_task(
                task(T2, A2, created_at=at(DAY1, 71), due_at=at(DAY1, 71 + 24 * 60), process_id=P2)
            ),
        ),
        Step(
            at(DAY1, 180),
            (
                UserTaskCompleted(
                    task_id=T2,
                    application_id=A2,
                    completed_by=UNDERWRITER,
                    result={"outcome": "COUNTER_OFFER"},
                ),
            ),
            lambda w: w.process.add_task(
                task(
                    T2,
                    A2,
                    created_at=at(DAY1, 71),
                    due_at=at(DAY1, 71 + 24 * 60),
                    process_id=P2,
                    status="done",
                    assignee_id=UNDERWRITER,
                )
            ),
        ),
        Step(
            at(DAY1, 181),
            (
                DecisionMade(
                    application_id=A2,
                    decision_id=d2b,
                    outcome="COUNTER_OFFER",
                    offer=terms("counter", "8000000", "25.0", expires),
                    decided_by="underwriter",
                    client_explanation="Можем предложить 8 млн ₽",
                    improvement_hints=["Подтвердите выручку выпиской — лимит может вырасти"],
                ),
            ),
            lambda w: w.decision.add_decision(
                decision(
                    A2,
                    "COUNTER_OFFER",
                    decided_at=at(DAY1, 181),
                    decision_id=d2b,
                    decided_by="underwriter",
                    reason_codes=("LIMIT_BY_REVENUE",),
                )
            ),
        ),
        Step(
            at(DAY1, 182),
            (moved(A2, ROMASHKA, "in_review", "offer_ready"),),
            card(
                A2,
                ROMASHKA,
                status="offer_ready",
                version=4,
                updated_at=at(DAY1, 182),
                offer=offer("8000000", "25.0", d2b, expires, kind="counter"),
            ),
        ),
        # --- A3: waits for an underwriter ----------------------------------------
        Step(
            DAY2,
            (
                submitted(A3, IVANOV, "OVERDRAFT", "1000000", 12),
                moved(A3, IVANOV, "draft", "submitted"),
            ),
            card(A3, IVANOV, **a3, updated_at=DAY2, submitted_at=DAY2),
        ),
        Step(
            at(DAY2, 2),
            (moved(A3, IVANOV, "submitted", "in_review"),),
            card(A3, IVANOV, status="in_review", version=3, updated_at=at(DAY2, 2)),
        ),
        Step(
            at(DAY2, 10),
            (
                DecisionMade(
                    application_id=A3,
                    decision_id=d3,
                    outcome="MANUAL_REVIEW",
                    decided_by="auto",
                    client_explanation="Заявку проверит специалист банка",
                ),
            ),
            both(
                lambda w: w.scoring.add_result(scoring_result(A3, 540, "D", ("cash_gap",))),
                lambda w: w.decision.add_decision(
                    decision(
                        A3,
                        "MANUAL_REVIEW",
                        decided_at=at(DAY2, 10),
                        decision_id=d3,
                        reason_codes=("SHORT_BUSINESS_HISTORY",),
                    )
                ),
            ),
        ),
        Step(
            at(DAY2, 11),
            (
                UserTaskCreated(
                    task_id=T3,
                    process_id=P3,
                    application_id=A3,
                    task_type="manual_review",
                    candidate_role="underwriter",
                    due_at=at(DAY2, 251),
                ),
            ),
            lambda w: w.process.add_task(
                task(T3, A3, created_at=at(DAY2, 11), due_at=at(DAY2, 251), process_id=P3)
            ),
        ),
        # --- A4: auto rejection ---------------------------------------------------
        Step(
            at(DAY2, 60),
            (
                submitted(A4, IVANOV, "UNSECURED", "2000000", 36),
                moved(A4, IVANOV, "draft", "submitted"),
            ),
            card(A4, IVANOV, **a4, updated_at=at(DAY2, 60), submitted_at=at(DAY2, 60)),
        ),
        Step(
            at(DAY2, 65),
            (moved(A4, IVANOV, "submitted", "in_review"),),
            card(A4, IVANOV, status="in_review", version=3, updated_at=at(DAY2, 65)),
        ),
        Step(
            at(DAY2, 80),
            (
                DecisionMade(
                    application_id=A4,
                    decision_id=d4,
                    outcome="REJECT",
                    decided_by="auto",
                    client_explanation="Сейчас не можем выдать кредит",
                    improvement_hints=["Вернитесь, когда бизнесу будет больше 12 месяцев"],
                ),
            ),
            lambda w: w.decision.add_decision(
                decision(A4, "REJECT", decided_at=at(DAY2, 80), decision_id=d4)
            ),
        ),
        Step(
            at(DAY2, 81),
            (
                moved(A4, IVANOV, "in_review", "rejected"),
                ProcessCompleted(process_id=P4, application_id=A4, outcome="REJECT"),
            ),
            card(A4, IVANOV, status="rejected", version=4, updated_at=at(DAY2, 81)),
        ),
        # --- companies --------------------------------------------------------------
        Step(
            at(DAY2, 120),
            (MemberAdded(organization_id=ROMASHKA, account_id=ACCOUNTANT, role="accountant"),),
        ),
        Step(
            at(DAY2, 180),
            (PreApprovedOffersUpdated(organization_id=IVANOV),),
            lambda w: w.decision.set_pre_approved(
                IVANOV,
                [
                    pre_approved("OVERDRAFT", "5000000", "24"),
                    pre_approved("UNSECURED", "3000000", "22.5"),
                ],
            ),
        ),
    ]


def published(scenario: list[Step]) -> list[tuple[Step, dict[str, Any]]]:
    """Envelopes with stable ids, each next to the step that publishes it."""
    result = []
    for step in scenario:
        for message in step.messages:
            event_id = uid(f"event-{len(result)}")
            result.append((step, envelope(message, step.at, event_id)))
    return result
