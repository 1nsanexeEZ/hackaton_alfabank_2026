from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from src.modules.decision.facade import PreApprovedOfferDTO

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
