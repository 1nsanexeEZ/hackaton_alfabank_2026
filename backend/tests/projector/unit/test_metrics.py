from datetime import date, timedelta
from typing import Any

from src.modules.projector.domain.metrics import DailyMetrics, MetricsSummary
from src.modules.projector.domain.read_models import ApplicationOverview
from tests.projector.unit.factories import T0, overview

DAY = date(2026, 10, 20)


def decided(outcome: str, by: str, after: timedelta, **changes: Any) -> ApplicationOverview:
    row = overview(**changes)
    row.record_decision(outcome, by, T0 + after)
    return row


def test_cell_counts_submissions_decisions_and_routing() -> None:
    rows = [
        decided("APPROVE", "auto", timedelta(minutes=10)),
        decided("COUNTER_OFFER", "underwriter", timedelta(hours=2)),
        decided("REJECT", "auto", timedelta(minutes=20)),
        overview(),  # submitted, not decided yet
        overview(product_code="OVERDRAFT"),  # another product
        overview(submitted_at=T0 - timedelta(days=1)),  # submitted the day before
    ]
    rows[1].record_decision("MANUAL_REVIEW", "auto", T0 + timedelta(minutes=5))

    cell = DailyMetrics.compute(DAY, "UNSECURED", rows)

    assert (cell.submitted, cell.approved, cell.counter_offers, cell.rejected) == (4, 1, 1, 1)
    assert (cell.manual_reviews, cell.auto_decisions, cell.decided) == (1, 2, 3)
    assert cell.decision_time_total_sec == 600 + 7200 + 1200
    assert cell.avg_time_to_decision_sec == 3000.0
    assert not cell.is_empty


def test_decision_counts_on_its_own_day() -> None:
    row = decided("APPROVE", "auto", timedelta(days=1))
    assert DailyMetrics.compute(DAY, "UNSECURED", [row]).decided == 0
    next_day = DailyMetrics.compute(DAY + timedelta(days=1), "UNSECURED", [row])
    assert next_day.approved == 1 and next_day.submitted == 0
    assert next_day.avg_time_to_decision_sec == 86400.0


def test_empty_cell() -> None:
    cell = DailyMetrics.compute(DAY, "UNSECURED", [])
    assert cell.is_empty and cell.avg_time_to_decision_sec is None


def test_summary_share_of_auto_decisions_and_average_time() -> None:
    cells = [
        DailyMetrics(
            DAY,
            "UNSECURED",
            submitted=3,
            approved=2,
            auto_decisions=2,
            decision_time_total_sec=1200,
            decision_time_count=2,
        ),
        DailyMetrics(
            DAY,
            "CREDIT_LINE",
            submitted=1,
            counter_offers=1,
            manual_reviews=1,
            decision_time_total_sec=7260,
            decision_time_count=1,
        ),
    ]
    summary = MetricsSummary.of(cells)
    assert (summary.submitted, summary.decided) == (4, 3)
    assert summary.auto_decision_share == 0.6667
    assert summary.avg_time_to_decision_sec == 2820.0


def test_summary_without_decisions() -> None:
    summary = MetricsSummary.of([DailyMetrics(DAY, "UNSECURED", submitted=2)])
    assert summary.decided == 0
    assert summary.auto_decision_share is None and summary.avg_time_to_decision_sec is None
