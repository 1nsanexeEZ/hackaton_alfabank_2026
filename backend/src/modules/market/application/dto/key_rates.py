from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

# `settings` — no stored rate is in force, KEY_RATE from the settings is used.
KeyRateOrigin = Literal["admin", "cbr", "settings"]


@dataclass(frozen=True, slots=True)
class KeyRateDTO:
    """The key rate in force on a day, % a year."""

    value: Decimal
    effective_from: date | None  # None — the value from the settings
    source: KeyRateOrigin


@dataclass(frozen=True, slots=True)
class KeyRateCreate:
    value: Decimal
    effective_from: date
    decided_on: date | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class KeyRateRecordDTO:
    value: Decimal
    effective_from: date
    decided_on: date | None
    source: KeyRateOrigin
    note: str | None
    created_at: datetime | None
    in_force: bool  # the rate in force today
    removable: bool  # not in force yet (or from today): may be deleted


@dataclass(frozen=True, slots=True)
class KeyRateHistoryDTO:
    current: KeyRateDTO
    items: list[KeyRateRecordDTO]  # newest effective_from first
