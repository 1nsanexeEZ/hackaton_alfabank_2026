from datetime import date, timedelta
from uuid import uuid4

import pytest

from src.modules.projector.domain.read_models import (
    OrganizationDashboard,
    action_required,
    has_cash_gap,
    queue_statuses,
    task_stage,
)
from tests.projector.unit.factories import T0, overview, queue_item


@pytest.mark.parametrize(
    "status,expected",
    [
        ("info_requested", "info"),
        ("offer_ready", "offer"),
        ("signing", "sign"),
        ("in_review", "none"),
        ("rejected", "none"),
    ],
)
def test_action_required_follows_the_status(status: str, expected: str) -> None:
    assert action_required(status) == expected


def test_newer_card_replaces_fields() -> None:
    row = overview()
    assert row.take_card(overview(status="offer_ready", source_version=4))
    assert row.status == "offer_ready" and row.source_version == 4


def test_older_card_is_ignored() -> None:
    row = overview(status="offer_ready", source_version=5)
    assert not row.take_card(overview(status="in_review", source_version=4))
    assert row.status == "offer_ready" and row.source_version == 5


def test_the_same_version_is_taken_again() -> None:
    row = overview(source_version=4)
    assert row.take_card(overview(client_stage="Проверяем данные", source_version=4))
    assert row.client_stage == "Проверяем данные"


def test_card_refresh_keeps_decision_facts() -> None:
    row = overview()
    row.record_decision("APPROVE", "auto", T0 + timedelta(minutes=10))
    row.take_card(overview(source_version=4))
    assert row.decision_outcome == "APPROVE" and row.time_to_decision_sec == 600


def test_first_final_decision_wins_whatever_the_order() -> None:
    early, late = T0 + timedelta(minutes=10), T0 + timedelta(hours=2)
    in_order, reversed_order = overview(), overview()

    in_order.record_decision("APPROVE", "auto", early)
    assert not in_order.record_decision("COUNTER_OFFER", "underwriter", late)
    reversed_order.record_decision("COUNTER_OFFER", "underwriter", late)
    assert reversed_order.record_decision("APPROVE", "auto", early)

    for row in (in_order, reversed_order):
        assert (row.decision_outcome, row.decided_by, row.decided_at) == ("APPROVE", "auto", early)
        assert row.time_to_decision_sec == 600


def test_repeated_decision_changes_nothing() -> None:
    row = overview()
    assert row.record_decision("REJECT", "auto", T0 + timedelta(minutes=5))
    assert not row.record_decision("REJECT", "auto", T0 + timedelta(minutes=5))


def test_manual_review_is_remembered_but_is_not_a_decision() -> None:
    row = overview()
    assert row.record_decision("MANUAL_REVIEW", "auto", T0 + timedelta(minutes=3))
    assert row.manual_review_at == T0 + timedelta(minutes=3)
    assert row.decided_at is None and row.time_to_decision_sec is None
    assert not row.record_decision("REQUEST_INFO", "auto", T0 + timedelta(minutes=4))


def test_time_to_decision_needs_submission() -> None:
    row = overview(submitted_at=None)
    row.record_decision("APPROVE", "auto", T0)
    assert row.time_to_decision_sec is None


def test_metric_cells_cover_submission_decision_and_routing_days() -> None:
    row = overview()
    row.record_decision("MANUAL_REVIEW", "auto", T0 + timedelta(hours=1))
    row.record_decision("APPROVE", "underwriter", T0 + timedelta(days=1))
    assert row.metric_cells() == {
        (date(2026, 10, 20), "UNSECURED"),
        (date(2026, 10, 21), "UNSECURED"),
    }


def test_task_stage_only_moves_forward() -> None:
    assert task_stage("open") < task_stage("in_progress") < task_stage("done")
    assert task_stage("done") == task_stage("cancelled")
    item = queue_item(status="done", source_version=task_stage("done"))
    assert not item.take_task(queue_item(status="open", source_version=task_stage("open")))
    assert item.status == "done"


def test_task_fields_follow_a_newer_read() -> None:
    item = queue_item()
    assignee = uuid4()
    taken = queue_item(status="in_progress", assignee_id=assignee, source_version=1)
    assert item.take_task(taken)
    assert item.status == "in_progress" and item.assignee_id == assignee


@pytest.mark.parametrize(
    "status,expected",
    [
        ("open", ("open", "in_progress")),
        ("closed", ("done", "cancelled")),
        ("done", ("done",)),
    ],
)
def test_queue_status_filter(status: str, expected: tuple[str, ...]) -> None:
    assert queue_statuses(status) == expected


def test_overdue_only_while_open() -> None:
    due = T0 + timedelta(hours=4)
    later = due + timedelta(minutes=1)
    assert queue_item(due_at=due).is_overdue(later)
    assert not queue_item(due_at=due).is_overdue(due - timedelta(minutes=1))
    assert not queue_item(due_at=None).is_overdue(later)
    assert not queue_item(due_at=due, status="done").is_overdue(later)


@pytest.mark.parametrize(
    "flags,expected",
    [(("cash_gap",), True), (("CASH_GAP_FORECAST", "x"), True), (("low_revenue",), False)],
)
def test_cash_gap_flag(flags: tuple[str, ...], expected: bool) -> None:
    assert has_cash_gap(flags) is expected


def test_dashboard_activity_never_goes_back() -> None:
    dashboard = OrganizationDashboard(uuid4())
    dashboard.touch(T0 + timedelta(hours=1))
    dashboard.touch(T0)
    assert dashboard.last_activity_at == T0 + timedelta(hours=1)
