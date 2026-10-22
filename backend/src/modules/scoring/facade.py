"""Scoring contract: the explainable score of an application and a quick
estimate for pre-approval."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

Grade = Literal["A", "B", "C", "D", "E"]


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


class ScoringFacade(Protocol):
    async def get_result(self, application_id: UUID) -> ScoringResultDTO | None: ...

    def estimate(self, company: CompanyProfileDTO, amount: Decimal | None = None) -> EstimateDTO:
        """No application, nothing stored: used for pre-approved offers."""
        ...
