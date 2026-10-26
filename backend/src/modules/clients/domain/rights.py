"""Rights inside a company (not to be confused with token permissions).

| Role             | view | submit_application | sign         | manage_members | edit_financials |
|------------------|------|--------------------|--------------|----------------|-----------------|
| owner / director | ✓    | ✓                  | if confirmed | ✓              | ✓               |
| accountant       | ✓    | ✓                  | by valid PoA | —              | ✓               |
| employee         | ✓    | by valid PoA       | by valid PoA | —              | —               |

PoA — power of attorney (доверенность) with that permission in its scope.

Confirmed authority of a head: by the registry, or by a power of attorney that
is valid at `now` and covers `sign`. An expired power of attorney gives nothing.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Self

from src.core.exceptions.exceptions import ValidationError
from src.modules.clients.domain.enums import Authority, MemberRole, OrgPermission

P = OrgPermission
R = MemberRole

HEAD_ROLES: frozenset[MemberRole] = frozenset({R.OWNER, R.DIRECTOR})

ROLE_PERMISSIONS: dict[MemberRole, frozenset[OrgPermission]] = {
    R.OWNER: frozenset({P.VIEW, P.SUBMIT_APPLICATION, P.MANAGE_MEMBERS, P.EDIT_FINANCIALS}),
    R.DIRECTOR: frozenset({P.VIEW, P.SUBMIT_APPLICATION, P.MANAGE_MEMBERS, P.EDIT_FINANCIALS}),
    R.ACCOUNTANT: frozenset({P.VIEW, P.SUBMIT_APPLICATION, P.EDIT_FINANCIALS}),
    R.EMPLOYEE: frozenset({P.VIEW}),
}

# What a power of attorney may grant on top of the role.
DELEGABLE_PERMISSIONS: frozenset[OrgPermission] = frozenset({P.SUBMIT_APPLICATION, P.SIGN})

# Stored ones load up to this; a new one is checked stricter by `PowerOfAttorney.issue`.
MAX_POA_NUMBER_LENGTH = 64
ISSUED_POA_NUMBER_LENGTH = 32
# "77 АА 1234567", "15/2026-Д", "Д-15": letters and digits separated by spaces, dots,
# slashes or hyphens; a digit is checked apart.
_POA_NUMBER = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+(?:[ ./-]+[0-9A-Za-zА-Яа-яЁё]+)*")


def _invalid(field_name: str, code: str, message: str) -> ValidationError:
    return ValidationError(message, details={"field": field_name, "code": code})


@dataclass(frozen=True, slots=True)
class PowerOfAttorney:
    """Доверенность: valid from `issued_at` to `valid_until` inclusive (UTC dates)."""

    number: str
    issued_at: date
    valid_until: date
    scope: frozenset[OrgPermission]

    def __post_init__(self) -> None:
        if not self.number.strip() or len(self.number) > MAX_POA_NUMBER_LENGTH:
            raise _invalid("number", "invalid", "Power of attorney number is empty or too long")
        if self.valid_until < self.issued_at:
            raise _invalid("valid_until", "before_issue", "Validity ends before the issue date")
        if not self.scope:
            raise _invalid("scope", "empty", "Power of attorney must grant something")
        if not self.scope <= DELEGABLE_PERMISSIONS:
            raise _invalid(
                "scope", "not_delegable", "Only submit_application and sign can be delegated"
            )

    @classmethod
    def issue(
        cls, number: str, issued_at: date, valid_until: date, scope: frozenset[OrgPermission]
    ) -> Self:
        """A new one: the number without the "№" sign and extra spaces, in the format above."""
        number = normalize_poa_number(number)
        if (
            len(number) > ISSUED_POA_NUMBER_LENGTH
            or not _POA_NUMBER.fullmatch(number)
            or not any(c.isdigit() for c in number)
        ):
            raise _invalid(
                "number",
                "invalid_format",
                "Power of attorney number: letters and digits separated by spaces, dots, "
                f"slashes or hyphens, with at least one digit, up to {ISSUED_POA_NUMBER_LENGTH}",
            )
        return cls(number, issued_at, valid_until, scope)

    def same_number(self, other: "PowerOfAttorney") -> bool:
        return _number_key(self.number) == _number_key(other.number)

    def is_valid(self, now: datetime) -> bool:
        return self.issued_at <= now.date() <= self.valid_until

    def is_expired(self, now: datetime) -> bool:
        return self.valid_until < now.date()

    def grants(self, permission: OrgPermission, now: datetime) -> bool:
        return permission in self.scope and self.is_valid(now)


def normalize_poa_number(number: str) -> str:
    """`" № 77  АА 1234567"` -> `"77 АА 1234567"`."""
    return " ".join(number.strip().removeprefix("№").split())


def _number_key(number: str) -> str:
    """Numbers that differ only in case and spaces are one number."""
    return "".join(number.split()).casefold()


def permissions_of(
    role: MemberRole,
    authority: Authority,
    power_of_attorney: PowerOfAttorney | None,
    now: datetime,
) -> frozenset[OrgPermission]:
    granted = set(ROLE_PERMISSIONS[role])
    if role in HEAD_ROLES and authority is Authority.REGISTRY:
        granted.add(P.SIGN)
    if power_of_attorney is not None and power_of_attorney.is_valid(now):
        granted |= power_of_attorney.scope
    return frozenset(granted)


def ordered(permissions: frozenset[OrgPermission]) -> list[OrgPermission]:
    """In the order of the table, for stable API answers."""
    return [p for p in OrgPermission if p in permissions]
