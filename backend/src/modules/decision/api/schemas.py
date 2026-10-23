from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from src.modules.decision.facade import (
    FounderPrescreenDTO,
    PreApprovedOfferDTO,
    ProjectAssessmentDTO,
)

PRE_APPROVAL_NOTE = "Предварительно: окончательное решение — после проверки заявки."

Basis = Literal["estimate", "full", "project"]
_BASES: dict[str, Basis] = {"full": "full", "project": "project"}


class PreApprovedOfferRead(BaseModel):
    product_code: str
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    valid_until: date
    # project — by a startup's project assessment (business plan and financial model).
    basis: Basis
    note: str = PRE_APPROVAL_NOTE

    @classmethod
    def of(cls, offer: PreApprovedOfferDTO) -> "PreApprovedOfferRead":
        return cls(
            product_code=offer.product_code,
            max_amount=offer.max_amount,
            rate_from=offer.rate_from,
            term_max_months=offer.term_max_months,
            valid_until=offer.valid_until,
            basis=_BASES.get(offer.basis, "estimate"),
        )


class FounderRead(BaseModel):
    account_id: UUID
    name: str


class PrescreenReasonRead(BaseModel):
    code: str
    passed: bool
    message: str


class FounderPrescreenRead(BaseModel):
    """`failed` — «отказ (стартап)»: клиенту — `reasons[].message`. Действует 30 дней; после
    `valid_until` для заявки на STARTUP нужен новый."""

    status: Literal["passed", "failed"]
    founder: FounderRead
    checked_at: datetime
    valid_until: datetime
    valid: bool
    reasons: list[PrescreenReasonRead]

    @classmethod
    def of(cls, prescreen: FounderPrescreenDTO) -> "FounderPrescreenRead":
        return cls(
            status=prescreen.status,
            founder=FounderRead(
                account_id=prescreen.founder_account_id, name=prescreen.founder_name
            ),
            checked_at=prescreen.checked_at,
            valid_until=prescreen.valid_until,
            valid=prescreen.valid,
            reasons=[
                PrescreenReasonRead(code=r.code, passed=r.passed, message=r.message)
                for r in prescreen.reasons
            ],
        )


class ProjectReasonRead(BaseModel):
    code: str
    passed: bool
    message: str


class ProjectAssessmentRead(BaseModel):
    """`passed` — «вам предодобрен кредит»: `product_code` до `max_amount`, заявка — в пределах.
    `failed` — клиенту `reasons[].message`, без порогов. Действует 30 дней; бизнес-план
    поменяли (`plan_revision` отстал) — оценку запускают заново."""

    status: Literal["passed", "failed"]
    product_code: str
    max_amount: Decimal | None
    plan_revision: int
    checked_at: datetime
    valid_until: datetime
    valid: bool
    reasons: list[ProjectReasonRead]

    @classmethod
    def of(cls, assessment: ProjectAssessmentDTO) -> "ProjectAssessmentRead":
        return cls(
            status=assessment.status,
            product_code=assessment.product_code,
            max_amount=assessment.max_amount,
            plan_revision=assessment.plan_revision,
            checked_at=assessment.checked_at,
            valid_until=assessment.valid_until,
            valid=assessment.valid,
            reasons=[
                ProjectReasonRead(code=r.code, passed=r.passed, message=r.message)
                for r in assessment.reasons
            ],
        )
