"""A key rate of the Bank of Russia from a date on. The rate in force on a day is the record
with the latest `effective_from` not after that day."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from src.modules.market.domain.enums import RateSource
from src.modules.market.domain.exceptions import InvalidKeyRateError

NOTE_MAX_LENGTH = 500
CENT = Decimal("0.01")


@dataclass(slots=True)
class KeyRate:
    effective_from: date
    value: Decimal  # % a year
    source: RateSource
    decided_on: date | None = None  # the board's decision, on or before effective_from
    note: str | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    # When KeyRateChanged went out for it; None — not yet (a future rate, or not announced).
    announced_at: datetime | None = None

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.value <= Decimal(100):
            raise InvalidKeyRateError("The key rate is from 0 to 100", "value")
        if self.value != self.value.quantize(CENT):
            raise InvalidKeyRateError("The key rate has at most two decimals", "value")
        self.value = self.value.quantize(CENT)
        if self.decided_on is not None and self.decided_on > self.effective_from:
            raise InvalidKeyRateError(
                "The decision date is on or before the effective date", "decided_on"
            )
        if self.note is not None and len(self.note) > NOTE_MAX_LENGTH:
            raise InvalidKeyRateError(f"The note is at most {NOTE_MAX_LENGTH} characters", "note")

    def can_be_removed(self, today: date) -> bool:
        """Only a rate not in force yet, or entered by mistake today: past rates are history,
        decisions were taken by them."""
        return self.effective_from >= today
