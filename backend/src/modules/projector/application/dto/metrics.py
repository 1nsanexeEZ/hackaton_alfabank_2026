"""Back office metrics by day and product."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DailyMetricsDTO:
    day: date
    product_code: str
    submitted: int
    approved: int
    counter_offers: int
    rejected: int
    manual_reviews: int
    auto_decisions: int
    avg_time_to_decision_sec: float | None


@dataclass(frozen=True, slots=True)
class BackofficeMetricsDTO:
    date_from: date
    date_to: date
    rows: tuple[DailyMetricsDTO, ...]
    submitted: int
    decided: int
    auto_decision_share: float | None
    avg_time_to_decision_sec: float | None
