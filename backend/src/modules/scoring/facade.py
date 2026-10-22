"""Scoring contract: the explainable score of an application and a quick
estimate for pre-approval."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

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
    # Top three features by the points lost.
    reason_codes: tuple[str, ...] = ()


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


class ScoringFacade(Protocol):
    async def get_result(self, application_id: UUID) -> ScoringResultDTO | None: ...

    def estimate(self, company: CompanyProfileDTO, amount: Decimal | None = None) -> EstimateDTO:
        """No application, nothing stored: used for pre-approved offers. A new
        client (segment `new_client`) is scored only on an application."""
        ...
