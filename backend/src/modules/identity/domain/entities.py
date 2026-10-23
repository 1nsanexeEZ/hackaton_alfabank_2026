import calendar
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.modules.identity.domain.enums import (
    CONSENT_TEXT_VERSIONS,
    CONSENT_VALIDITY_MONTHS,
    ConsentType,
)
from src.modules.identity.domain.exceptions import OrphanedPoliciesError

# --- roles ---------------------------------------------------------------------------------


def normalize_role_rules(
    permissions: Sequence[Permissions],
    policies: Mapping[Permissions, Sequence[Policies]],
) -> tuple[list[str], dict[str, list[str]]]:
    """Dedupe and check that policies are attached only to granted permissions."""
    granted = list(dict.fromkeys(p.value for p in permissions))
    orphaned = sorted(p.value for p in policies if p.value not in granted)
    if orphaned:
        raise OrphanedPoliciesError(orphaned)
    rules = {
        permission.value: list(dict.fromkeys(policy.value for policy in attached))
        for permission, attached in policies.items()
    }
    return granted, rules


@dataclass(slots=True)
class Role:
    """A named set of permissions; `policies` narrow a permission to rows."""

    id: UUID
    name: str
    description: str
    # ["accounts.read", ...]
    permissions: list[str]
    # {"accounts.read": ["not_deleted"], "accounts.create": []}
    policies: dict[str, list[str]]
    # Filled by the repository once the role is stored.
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        permissions: Sequence[Permissions],
        policies: Mapping[Permissions, Sequence[Policies]],
    ) -> Self:
        granted, rules = normalize_role_rules(permissions, policies)
        return cls(
            id=uuid4(), name=name, description=description, permissions=granted, policies=rules
        )

    def change_rules(
        self,
        permissions: Sequence[Permissions] | None,
        policies: Mapping[Permissions, Sequence[Policies]] | None,
    ) -> None:
        """None keeps the current value. Without new policies the current ones stay,
        except those of permissions that are taken away."""
        if permissions is None:
            permissions = [Permissions(p) for p in self.permissions]
        if policies is None:
            policies = {
                Permissions(k): [Policies(p) for p in v]
                for k, v in self.policies.items()
                if Permissions(k) in permissions
            }
        self.permissions, self.policies = normalize_role_rules(permissions, policies)


# --- personal consents ---------------------------------------------------------------------


def add_months(moment: datetime, months: int) -> datetime:
    """Same day `months` later; a missing day (31 → 30 April) moves to the month's end."""
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def consent_valid_until(type: ConsentType, given_at: datetime) -> datetime | None:
    months = CONSENT_VALIDITY_MONTHS[type]
    return None if months is None else add_months(given_at, months)


@dataclass(slots=True)
class Consent:
    """A personal consent of the account's owner (152-FZ, 218-FZ). Never rewritten:
    a new consent is a new record, a revocation only sets `revoked_at`."""

    id: UUID
    account_id: UUID
    type: ConsentType
    given_at: datetime
    # None — valid until revoked.
    valid_until: datetime | None
    revoked_at: datetime | None
    # Edition of the consent text the person was shown.
    text_version: str
    ip: str | None = None
    user_agent: str | None = None

    @classmethod
    def give(
        cls,
        account_id: UUID,
        type: ConsentType,
        now: datetime,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> Self:
        return cls(
            id=uuid4(),
            account_id=account_id,
            type=type,
            given_at=now,
            valid_until=consent_valid_until(type, now),
            revoked_at=None,
            text_version=CONSENT_TEXT_VERSIONS[type],
            ip=ip,
            user_agent=user_agent[:512] if user_agent else None,
        )

    def is_active(self, now: datetime) -> bool:
        if self.revoked_at is not None:
            return False
        return self.valid_until is None or self.valid_until > now

    def revoke(self, now: datetime) -> None:
        self.revoked_at = now
