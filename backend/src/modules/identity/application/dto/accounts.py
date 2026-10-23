from dataclasses import dataclass, fields
from datetime import datetime
from typing import Self
from uuid import UUID

from src.modules.identity.application.dto.common import UNSET, Unset, stored
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.profile import Profile


@dataclass(frozen=True, slots=True)
class RoleRefDTO:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class ProfileDTO:
    last_name: str
    first_name: str
    middle_name: str | None = None
    position: str | None = None

    @classmethod
    def from_entity(cls, profile: Profile) -> Self:
        return cls(
            last_name=profile.last_name,
            first_name=profile.first_name,
            middle_name=profile.middle_name,
            position=profile.position,
        )

    def to_entity(self) -> Profile:
        return Profile(
            last_name=self.last_name,
            first_name=self.first_name,
            middle_name=self.middle_name,
            position=self.position,
        )


@dataclass(frozen=True, slots=True)
class AccountDTO:
    id: UUID
    email: str | None
    phone: str | None
    role: RoleRefDTO
    profile: ProfileDTO
    created_at: datetime
    deleted_at: datetime | None

    @classmethod
    def from_entity(cls, account: Account) -> Self:
        return cls(
            id=account.id,
            email=account.email,
            phone=account.phone,
            role=RoleRefDTO(id=account.role.id, name=account.role.name),
            profile=ProfileDTO.from_entity(account.profile),
            created_at=stored(account.created_at),
            deleted_at=account.deleted_at,
        )


@dataclass(frozen=True, slots=True)
class CreateAccountDTO:
    email: str | None
    phone: str | None
    password: str
    role_id: UUID
    profile: ProfileDTO


@dataclass(frozen=True, slots=True)
class ProfileChangesDTO:
    last_name: str | None | Unset = UNSET
    first_name: str | None | Unset = UNSET
    middle_name: str | None | Unset = UNSET
    position: str | None | Unset = UNSET

    def changes(self) -> dict[str, str | None]:
        """Only the fields that were sent."""
        changed: dict[str, str | None] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if value is not UNSET:
                changed[item.name] = value
        return changed


@dataclass(frozen=True, slots=True)
class UpdateAccountDTO:
    """`email`/`phone`: UNSET keeps, None clears. The rest: None keeps."""

    email: str | None | Unset = UNSET
    phone: str | None | Unset = UNSET
    password: str | None = None
    role_id: UUID | None = None
    profile: ProfileChangesDTO | None = None
