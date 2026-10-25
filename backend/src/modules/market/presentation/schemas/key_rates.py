import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.market.application.dto.key_rates import KeyRateOrigin
from src.modules.market.domain.key_rate import NOTE_MAX_LENGTH


class KeyRateRead(BaseModel):
    """The key rate in force: `source: settings` and `effective_from: null` — nothing is
    entered for this day, `KEY_RATE` from the settings is used."""

    model_config = ConfigDict(from_attributes=True)

    value: Decimal = Field(examples=["14.00"])
    effective_from: dt.date | None
    source: KeyRateOrigin


class KeyRateCreate(BaseModel):
    value: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2, examples=["13.50"])
    effective_from: dt.date = Field(
        description="Moscow date the rate is in force from (the next working day after the "
        "board's decision, as the Bank of Russia announces)"
    )
    decided_on: dt.date | None = Field(
        default=None, description="Date of the board's decision, on or before effective_from"
    )
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)


class KeyRateRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: Decimal
    effective_from: dt.date
    decided_on: dt.date | None
    source: KeyRateOrigin
    note: str | None
    created_at: dt.datetime | None
    in_force: bool = Field(description="The rate in force today")
    removable: bool = Field(description="Not in force yet (or from today): may be deleted")


class KeyRateHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current: KeyRateRead
    items: list[KeyRateRecordRead] = Field(description="Newest effective_from first")
