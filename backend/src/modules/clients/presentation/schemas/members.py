from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.types import SafeString
from src.modules.clients.application.dto.members import GrantPowerOfAttorneyDTO
from src.modules.clients.domain.enums import MemberRole

Role = Literal["owner", "director", "accountant", "employee"]
Delegable = Literal["submit_application", "sign"]


class PowerOfAttorneyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: str
    issued_at: date
    valid_until: date
    scope: list[str]
    is_valid: bool


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: UUID
    role: Role
    authority: Literal["registry", "power_of_attorney", "unconfirmed"]
    power_of_attorney: PowerOfAttorneyRead | None
    # Effective now: an expired power of attorney gives nothing.
    permissions: list[str]
    added_at: datetime
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    position: str | None = None


class MemberCreate(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email or phone of the account")
    role: MemberRole


class MemberUpdate(BaseModel):
    role: MemberRole


class PowerOfAttorneyCreate(BaseModel):
    number: SafeString = Field(min_length=1, max_length=64)
    issued_at: date
    valid_until: date
    scope: list[Delegable] = Field(min_length=1)

    def to_dto(self) -> GrantPowerOfAttorneyDTO:
        return GrantPowerOfAttorneyDTO(
            number=self.number,
            issued_at=self.issued_at,
            valid_until=self.valid_until,
            scope=frozenset(self.scope),
        )
