"""Back office metrics by day and product.

A metrics cell is never incremented: it is recomputed from the application
overview rows that fall into it, so a repeated or late event cannot count twice.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from src.modules.projector.domain.read_models import ApplicationOverview, day_of

AUTO = "auto"


@dataclass(frozen=True, slots=True)
class DailyMetrics:
    day: date
    product_code: str
    submitted: int = 0
    approved: int = 0
    counter_offers: int = 0
    rejected: int = 0
    # Routed to an underwriter that day.
    manual_reviews: int = 0
    # First final decisions made without a person that day.
    auto_decisions: int = 0
    # Submitted -> first final decision, over the decisions of that day.
    decision_time_total_sec: int = 0
    decision_time_count: int = 0

    @classmethod
    def compute(
        cls, day: date, product_code: str, overviews: Iterable[ApplicationOverview]
    ) -> "DailyMetrics":
        submitted = approved = counter_offers = rejected = manual = auto = 0
        total_sec = timed = 0
        for row in overviews:
            if row.product_code != product_code:
                continue
            if row.submitted_at is not None and day_of(row.submitted_at) == day:
                submitted += 1
            if row.manual_review_at is not None and day_of(row.manual_review_at) == day:
                manual += 1
            if row.decided_at is None or day_of(row.decided_at) != day:
                continue
            approved += row.decision_outcome == "APPROVE"
            counter_offers += row.decision_outcome == "COUNTER_OFFER"
            rejected += row.decision_outcome == "REJECT"
            auto += row.decided_by == AUTO
            if row.time_to_decision_sec is not None:
                total_sec += row.time_to_decision_sec
                timed += 1
        return cls(
            day=day,
            product_code=product_code,
            submitted=submitted,
            approved=approved,
            counter_offers=counter_offers,
            rejected=rejected,
            manual_reviews=manual,
            auto_decisions=auto,
            decision_time_total_sec=total_sec,
            decision_time_count=timed,
        )

    @property
    def decided(self) -> int:
        return self.approved + self.counter_offers + self.rejected

    @property
    def avg_time_to_decision_sec(self) -> float | None:
        return _average(self.decision_time_total_sec, self.decision_time_count)

    @property
    def is_empty(self) -> bool:
        return not (self.submitted or self.decided or self.manual_reviews)


@dataclass(frozen=True, slots=True)
class MetricsSummary:
    submitted: int
    decided: int
    auto_decision_share: float | None
    avg_time_to_decision_sec: float | None

    @classmethod
    def of(cls, rows: Iterable[DailyMetrics]) -> "MetricsSummary":
        cells = list(rows)
        decided = sum(c.decided for c in cells)
        auto = sum(c.auto_decisions for c in cells)
        return cls(
            submitted=sum(c.submitted for c in cells),
            decided=decided,
            auto_decision_share=round(auto / decided, 4) if decided else None,
            avg_time_to_decision_sec=_average(
                sum(c.decision_time_total_sec for c in cells),
                sum(c.decision_time_count for c in cells),
            ),
        )


def _average(total_sec: int, count: int) -> float | None:
    return round(total_sec / count, 1) if count else None
