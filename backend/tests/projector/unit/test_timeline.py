from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.messaging.contracts.applications import (
    ApplicationInfoProvided,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferTerms,
)
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.clients import MemberAdded
from src.core.messaging.contracts.decision import (
    DecisionMade,
    ManualDecisionRejected,
    RequestedInfo,
)
from src.core.messaging.contracts.process import (
    ProcessCompleted,
    ProcessFailed,
    ProcessStarted,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.modules.projector.application.mappers.timeline import timeline_entry
from src.modules.projector.domain.timeline import BANK, CLIENT, TimelineEntry, entry_id

AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
APP, ORG, PROCESS, TASK = uuid4(), uuid4(), uuid4(), uuid4()


def entry(message: IntegrationMessage) -> TimelineEntry:
    result = timeline_entry(uuid4(), AT, message)
    assert result is not None
    return result


def test_status_change_is_a_client_entry() -> None:
    result = entry(
        ApplicationStatusChanged(
            application_id=APP,
            organization_id=ORG,
            from_status="in_review",
            to_status="offer_ready",
        )
    )
    assert (result.kind, result.audience, result.title) == (
        "status",
        CLIENT,
        "Готово предложение банка",
    )
    assert result.details["to_status"] == "offer_ready"


def test_unknown_status_still_gets_a_title() -> None:
    result = entry(
        ApplicationStatusChanged(
            application_id=APP, organization_id=ORG, from_status="x", to_status="archived"
        )
    )
    assert result.title == "Статус заявки: archived"


def test_client_stage_is_for_the_client_internal_step_is_for_the_bank() -> None:
    staged = entry(
        StepCompleted(
            process_id=PROCESS,
            application_id=APP,
            node_id="fetch",
            step_code="fetch_enrichment",
            client_stage="Проверяем данные о компании",
        )
    )
    internal = entry(
        StepCompleted(process_id=PROCESS, application_id=APP, node_id="n", step_code="score")
    )
    assert (staged.audience, staged.title, staged.kind) == (
        CLIENT,
        "Проверяем данные о компании",
        "stage",
    )
    assert staged.details == {"step_code": "fetch_enrichment"}
    assert internal.audience == BANK and "score" in internal.title


@pytest.mark.parametrize(
    "message,kind",
    [
        (
            ProcessStarted(process_id=PROCESS, application_id=APP, workflow_code="express_v1"),
            "stage",
        ),
        (ProcessCompleted(process_id=PROCESS, application_id=APP, outcome="APPROVE"), "stage"),
        (ProcessFailed(process_id=PROCESS, application_id=APP, reason="timeout"), "stage"),
        (
            UserTaskCreated(
                task_id=TASK,
                process_id=PROCESS,
                application_id=APP,
                task_type="manual_review",
                candidate_role="underwriter",
            ),
            "task",
        ),
        (
            UserTaskCompleted(
                task_id=TASK, application_id=APP, completed_by=uuid4(), result={"ok": True}
            ),
            "task",
        ),
        (ManualDecisionRejected(application_id=APP, task_id=TASK, reason="limits"), "decision"),
        (
            ApplicationInfoProvided(
                application_id=APP, organization_id=ORG, info_request_id=uuid4()
            ),
            "status",
        ),
    ],
    ids=["started", "completed", "failed", "task", "task-done", "rejected", "info"],
)
def test_bank_only_entries(message: IntegrationMessage, kind: str) -> None:
    result = entry(message)
    assert result.audience == BANK and result.kind == kind
    assert not result.visible_to(CLIENT) and result.visible_to(BANK)


def test_decision_entry_shows_the_client_what_he_may_see() -> None:
    result = entry(
        DecisionMade(
            application_id=APP,
            decision_id=uuid4(),
            outcome="COUNTER_OFFER",
            offer=OfferTerms(
                kind="counter",
                amount=Decimal("8000000"),
                term_months=24,
                rate=Decimal("25.0"),
                monthly_payment=Decimal("427000"),
                expires_at=AT + timedelta(days=30),
            ),
            decided_by="underwriter",
            requested_info=RequestedInfo(comment="—"),
            client_explanation="Можем предложить 8 млн",
            improvement_hints=["Подтвердите выручку выпиской"],
        )
    )
    assert (result.kind, result.audience) == ("decision", CLIENT)
    assert result.title == "Банк предложил другие условия"
    assert result.details["offer"]["amount"] == "8000000"
    assert result.details["improvement_hints"] == ["Подтвердите выручку выпиской"]
    assert "decision_id" not in result.details and "application_id" not in result.details


@pytest.mark.parametrize(
    "message",
    [
        ApplicationSubmitted(
            application_id=APP,
            organization_id=ORG,
            product_code="UNSECURED",
            amount=Decimal("1"),
            term_months=12,
            purpose="working_capital",
        ),
        OfferAccepted(application_id=APP, organization_id=ORG),
        MemberAdded(organization_id=ORG, account_id=uuid4(), role="accountant"),
    ],
    ids=["submitted", "accepted", "member"],
)
def test_events_covered_by_a_status_change_make_no_entry(message: IntegrationMessage) -> None:
    assert timeline_entry(uuid4(), AT, message) is None


def test_entry_id_is_derived_from_the_event() -> None:
    event_id = uuid4()
    message = OfferAccepted(application_id=APP, organization_id=ORG)
    changed = ApplicationStatusChanged(
        application_id=APP, organization_id=ORG, from_status="offer_ready", to_status="signing"
    )
    first = timeline_entry(event_id, AT, changed)
    again = timeline_entry(event_id, AT, changed)
    assert first is not None and again is not None
    assert first.id == again.id == entry_id(event_id)
    assert timeline_entry(event_id, AT, message) is None
