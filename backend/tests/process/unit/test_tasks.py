from datetime import timedelta
from uuid import uuid4

import pytest

from src.core.exceptions.exceptions import (
    ConflictError,
    InvalidStatusTransitionError,
    PermissionDeniedError,
    ValidationError,
)
from src.modules.process.domain.enums import TaskStatus
from src.modules.process.domain.events import UserTaskCompleted
from src.modules.process.domain.steps import UNDERWRITER_FORM
from src.modules.process.domain.tasks import UserTask
from tests.process.unit.routes import NOW

ALICE, BOB = uuid4(), uuid4()
APPROVE = {
    "decision": "approve",
    "amount": 3_000_000,
    "term_months": 24,
    "rate": 23.5,
    "comment": "Чистая история, выручка подтверждена",
}


def task() -> UserTask:
    return UserTask(
        id=uuid4(),
        process_id=uuid4(),
        application_id=uuid4(),
        node_id="underwriter_review",
        type="underwriter_review",
        candidate_role="underwriter",
        form_schema=UNDERWRITER_FORM,
        created_at=NOW,
        due_at=NOW + timedelta(hours=8),
    )


def test_claim_and_complete() -> None:
    t = task()
    t.claim(ALICE)
    t.claim(ALICE)  # again — no-op
    assert (t.status, t.assignee_id) == (TaskStatus.IN_PROGRESS, ALICE)
    t.complete(ALICE, APPROVE, NOW)
    assert t.status is TaskStatus.DONE and t.completed_by == ALICE
    assert t.result == {**APPROVE, "completed_by": str(ALICE)}
    [event] = t.pull_events()
    assert isinstance(event, UserTaskCompleted) and event.task_id == t.id


def test_taken_task_is_not_given_to_another() -> None:
    t = task()
    t.claim(ALICE)
    with pytest.raises(ConflictError):
        t.claim(BOB)


def test_only_the_assignee_closes() -> None:
    t = task()
    with pytest.raises(InvalidStatusTransitionError):
        t.complete(ALICE, APPROVE, NOW)  # not taken
    t.claim(ALICE)
    with pytest.raises(PermissionDeniedError):
        t.complete(BOB, APPROVE, NOW)


@pytest.mark.parametrize(
    "result,missing",
    [
        ({**APPROVE, "comment": "  "}, ["comment"]),
        ({k: v for k, v in APPROVE.items() if k != "comment"}, ["comment"]),
        ({**APPROVE, "decision": "maybe"}, ["decision"]),
        ({"decision": "counter_offer", "comment": "x"}, ["amount", "term_months", "rate"]),
        ({"decision": "request_info", "comment": "x"}, ["requested_documents"]),
    ],
)
def test_decision_must_be_complete(result: dict, missing: list[str]) -> None:
    t = task()
    t.claim(ALICE)
    with pytest.raises(ValidationError) as error:
        t.complete(ALICE, result, NOW)
    assert error.value.details == {"code": "invalid_result", "fields": missing}
    assert t.status is TaskStatus.IN_PROGRESS


def test_reject_needs_only_a_comment() -> None:
    t = task()
    t.claim(ALICE)
    t.complete(ALICE, {"decision": "reject", "comment": "Просрочки в БКИ"}, NOW)
    assert t.status is TaskStatus.DONE


def test_cancel_and_overdue() -> None:
    t = task()
    assert not t.is_overdue(NOW + timedelta(hours=7))
    assert t.is_overdue(NOW + timedelta(hours=9))
    assert t.cancel()
    assert not t.cancel()
    assert not t.is_overdue(NOW + timedelta(hours=9))
    with pytest.raises(InvalidStatusTransitionError):
        t.claim(ALICE)
