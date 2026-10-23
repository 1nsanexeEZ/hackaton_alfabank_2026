from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DisbursementReceipt:
    reference: str
    # True while payout goes through the mock of the core banking system.
    simulated: bool


class AbsClient(Protocol):
    """Core banking system (АБС): opens the loan account and pays the credit out."""

    async def disburse(
        self,
        application_id: UUID,
        number: str,
        organization_id: UUID,
        amount: Decimal,
        term_months: int,
        rate: Decimal,
    ) -> DisbursementReceipt: ...
