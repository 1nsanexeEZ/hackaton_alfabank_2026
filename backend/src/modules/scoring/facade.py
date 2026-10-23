"""Scoring contract: the explainable score of an application and a quick
estimate for pre-approval."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from src.modules.enrichment.facade import CreditHistoryDTO

# The PD model grades A–J by the probability of default; results of
# scorecard_v1 (before pd_model_v2) carry A–E and no `pd_12m`.
Grade = Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
Segment = Literal["legal_entity", "entrepreneur", "new_client"]


@dataclass(frozen=True, slots=True)
class FactorDTO:
    code: str
    value: str | None
    bin: str
    points: int
    direction: Literal["positive", "negative", "neutral"]
    client_hint: str | None = None


@dataclass(frozen=True, slots=True)
class MlScoreDTO:
    """The ML model's estimate, computed next to the PD model on the same input and graded
    on the same A–J scale, so the underwriter compares the two directly."""

    model_version: str
    pd_12m: Decimal
    score: int
    grade: Grade
    factors: tuple[FactorDTO, ...]
    # Top three features that lowered the score, by the points lost against their best bin.
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoringResultDTO:
    id: UUID
    application_id: UUID
    model_version: str
    score: int
    grade: Grade
    factors: tuple[FactorDTO, ...]
    flags: tuple[str, ...]
    data_completeness: Decimal
    computed_at: datetime
    segment: Segment | None = None
    scorecard: str | None = None
    # Probability of default within 12 months, a share: "0.0340" is 3.4%.
    pd_12m: Decimal | None = None
    # Top three features that lowered the score, by the points lost.
    reason_codes: tuple[str, ...] = ()
    # The ML model next to the PD model; None for results computed before it.
    ml: MlScoreDTO | None = None
    # "Is the data complete?": degraded — a critical source failed or too few features had
    # data, a person decides; reasons: `source_failed:<source>`, `completeness_below:<share>`.
    # None for results computed before it.
    quality: Literal["ok", "degraded"] | None = None
    quality_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompanyProfileDTO:
    legal_form: str
    business_age_months: int
    okved_main: str
    annual_revenue: Decimal | None
    previous_annual_revenue: Decimal | None
    verification_status: str
    registry_status: str


@dataclass(frozen=True, slots=True)
class EstimateDTO:
    score: int
    grade: Grade
    flags: tuple[str, ...]
    factors: tuple[FactorDTO, ...]
    segment: Segment | None = None
    pd_12m: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PrescreenReasonDTO:
    code: str  # no_history | no_current_overdue | no_serious_overdue | few_inquiries | debt_load
    passed: bool
    message: str  # for the client


@dataclass(frozen=True, slots=True)
class PersonPrescreenDTO:
    version: str
    passed: bool
    reasons: tuple[PrescreenReasonDTO, ...]


class ScoringFacade(Protocol):
    async def get_result(self, application_id: UUID) -> ScoringResultDTO | None: ...

    def estimate(self, company: CompanyProfileDTO, amount: Decimal | None = None) -> EstimateDTO:
        """No application, nothing stored: used for pre-approved offers. A new
        client (segment `new_client`) is scored only on an application."""
        ...

    def prescreen_person(self, history: CreditHistoryDTO | None) -> PersonPrescreenDTO:
        """A startup founder's own credit history instead of the turnover the
        company does not have yet. None — the bureau does not know the person."""
        ...
