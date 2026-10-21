"""Member of a company and the actor who changes the company."""

from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from src.clients.domain.rights import (
    Authority,
    MemberRole,
    OrgPermission,
    PowerOfAttorney,
    permissions_of,
)


@dataclass(frozen=True, slots=True)
class Actor:
    """A member of the company or the bank (seeds, back office). The bank is
    not bound by the rights table, a member is."""

    account_id: UUID | None
    is_bank: bool = False

    @classmethod
    def member(cls, account_id: UUID) -> Self:
        return cls(account_id)

    @classmethod
    def bank(cls, account_id: UUID | None = None) -> Self:
        return cls(account_id, is_bank=True)


@dataclass(slots=True)
class Member:
    """Entity inside the Organization aggregate: changed only through it."""

    account_id: UUID
    role: MemberRole
    authority: Authority
    added_at: datetime
    added_by: UUID | None = None
    power_of_attorney: PowerOfAttorney | None = None

    def permissions(self, now: datetime) -> frozenset[OrgPermission]:
        return permissions_of(self.role, self.authority, self.power_of_attorney, now)

    def can(self, permission: OrgPermission, now: datetime) -> bool:
        return permission in self.permissions(now)
