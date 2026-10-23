from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from src.modules.decision.facade import FounderPrescreenDTO, PreApprovedOfferDTO

PRE_APPROVAL_NOTE = "Предварительно: окончательное решение — после проверки заявки."


class PreApprovedOfferRead(BaseModel):
    product_code: str
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    valid_until: date
    basis: Literal["estimate", "full"]
    note: str = PRE_APPROVAL_NOTE

    @classmethod
    def of(cls, offer: PreApprovedOfferDTO) -> "PreApprovedOfferRead":
        return cls(
            product_code=offer.product_code,
            max_amount=offer.max_amount,
            rate_from=offer.rate_from,
            term_max_months=offer.term_max_months,
            valid_until=offer.valid_until,
            basis="full" if offer.basis == "full" else "estimate",
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
