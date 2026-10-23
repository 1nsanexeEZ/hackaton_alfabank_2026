"""Members of a company and their powers of attorney."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Self
from uuid import UUID

from src.modules.clients.domain.member import Member
from src.modules.clients.domain.rights import ordered
from src.modules.identity.facade import AccountRefDTO


@dataclass(frozen=True, slots=True)
class PowerOfAttorneyDTO:
    number: str
    issued_at: date
    valid_until: date
    scope: tuple[str, ...]
    is_valid: bool


@dataclass(frozen=True, slots=True)
class MemberDTO:
    account_id: UUID
    role: str
    authority: str
    power_of_attorney: PowerOfAttorneyDTO | None
    # Effective now: an expired power of attorney gives nothing.
    permissions: tuple[str, ...]
    added_at: datetime
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    position: str | None = None

    @classmethod
    def of(cls, member: Member, account: AccountRefDTO | None, now: datetime) -> Self:
        poa = member.power_of_attorney
        return cls(
            account_id=member.account_id,
            role=member.role.value,
            authority=member.authority.value,
            power_of_attorney=PowerOfAttorneyDTO(
                number=poa.number,
                issued_at=poa.issued_at,
                valid_until=poa.valid_until,
                scope=tuple(p.value for p in ordered(poa.scope)),
                is_valid=poa.is_valid(now),
            )
            if poa
            else None,
            permissions=tuple(p.value for p in ordered(member.permissions(now))),
            added_at=member.added_at,
            last_name=account.last_name if account else None,
            first_name=account.first_name if account else None,
            middle_name=account.middle_name if account else None,
            position=account.position if account else None,
        )


@dataclass(frozen=True, slots=True)
class GrantPowerOfAttorneyDTO:
    number: str
    issued_at: date
    valid_until: date
    # submit_application and/or sign.
    scope: frozenset[str]
