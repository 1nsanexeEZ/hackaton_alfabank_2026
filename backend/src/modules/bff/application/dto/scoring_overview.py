from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GradeCountDTO:
    grade: str
    pd: int  # applications with this PD-model grade
    ml: int  # with this ML-model grade


@dataclass(frozen=True, slots=True)
class ZonePairDTO:
    """Applications scored by both models with this pair of zones."""

    pd_zone: str
    ml_zone: str
    count: int


@dataclass(frozen=True, slots=True)
class VersionCountDTO:
    kind: Literal["pd", "ml", "policy"]
    version: str
    count: int


@dataclass(frozen=True, slots=True)
class ScoredApplicationDTO:
    application_id: UUID
    number: str
    company_name: str | None
    product_code: str
    amount: Decimal | None
    status: str
    submitted_at: datetime | None
    # The PD model; None — not scored (a stop factor before the models, or not yet).
    score: int | None
    grade: str | None
    pd_12m: Decimal | None
    ml_score: int | None
    ml_grade: str | None
    ml_pd_12m: Decimal | None
    ml_not_applicable: str | None
    quality: str | None
    models_disagree: bool  # both scored and their zones differ
    outcome: str | None
    decided_by_type: str | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoringOverviewDTO:
    """Counts are over `considered` submitted applications (the latest ones, up to the cap);
    `items` — the latest `limit` of them."""

    considered: int
    scored: int
    stopped_before_models: int
    with_ml: int
    models_agree: int
    degraded: int
    manual_review: int
    decided: int  # a final decision: approve, counter offer or reject
    decided_auto: int
    by_grade: tuple[GradeCountDTO, ...]
    zones: tuple[ZonePairDTO, ...]
    versions: tuple[VersionCountDTO, ...]
    items: tuple[ScoredApplicationDTO, ...]
