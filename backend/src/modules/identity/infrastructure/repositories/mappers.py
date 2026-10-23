"""Rows <-> domain entities."""

from datetime import UTC, datetime
from typing import Any, cast

from src.modules.identity.domain.account import Account
from src.modules.identity.domain.entities import Consent, Role
from src.modules.identity.domain.enums import ConsentType
from src.modules.identity.domain.profile import Profile
from src.modules.identity.infrastructure.database.models import (
    AccountModel,
    ConsentModel,
    ProfileModel,
    RoleModel,
)


def aware(moment: datetime) -> datetime:
    """sqlite gives back naive datetimes; they are UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _aware_or_none(moment: datetime | None) -> datetime | None:
    return None if moment is None else aware(moment)


def _same(stored: Any, value: Any) -> bool:
    if isinstance(stored, datetime) and isinstance(value, datetime):
        return aware(stored) == aware(value)
    return bool(stored == value)


def assign(row: Any, **values: Any) -> None:
    """Only what changed is assigned, so an unchanged row keeps its updated_at."""
    for name, value in values.items():
        if not _same(getattr(row, name), value):
            setattr(row, name, value)


# --- role ----------------------------------------------------------------------------------


def role_to_entity(row: RoleModel) -> Role:
    return Role(
        id=row.id,
        name=row.name,
        description=row.description,
        permissions=list(row.permissions),
        policies={k: list(v) for k, v in row.policies.items()},
        created_at=aware(row.created_at),
        updated_at=aware(row.updated_at),
    )


def role_to_row(role: Role) -> RoleModel:
    return RoleModel(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=list(role.permissions),
        policies={k: list(v) for k, v in role.policies.items()},
    )


def update_role_row(row: RoleModel, role: Role) -> None:
    assign(
        row,
        name=role.name,
        description=role.description,
        permissions=list(role.permissions),
        policies={k: list(v) for k, v in role.policies.items()},
    )


# --- account -------------------------------------------------------------------------------


def account_to_entity(row: AccountModel) -> Account:
    profile = row.profile
    return Account(
        id=row.id,
        email=row.email,
        phone=row.phone,
        password_hash=row.password_hash,
        role=role_to_entity(row.role),
        profile=Profile(
            last_name=profile.last_name,
            first_name=profile.first_name,
            middle_name=profile.middle_name,
            position=profile.position,
        ),
        created_at=aware(row.created_at),
        deleted_at=_aware_or_none(row.deleted_at),
    )


def account_to_row(account: Account) -> AccountModel:
    profile = account.profile
    return AccountModel(
        id=account.id,
        email=account.email,
        phone=account.phone,
        password_hash=account.password_hash,
        role_id=account.role.id,
        deleted_at=account.deleted_at,
        profile=ProfileModel(
            last_name=profile.last_name,
            first_name=profile.first_name,
            middle_name=profile.middle_name,
            position=profile.position,
        ),
    )


def update_account_row(row: AccountModel, account: Account) -> None:
    """The role is not touched here: the repository relinks it."""
    assign(
        row,
        email=account.email,
        phone=account.phone,
        password_hash=account.password_hash,
        deleted_at=account.deleted_at,
    )
    profile = account.profile
    assign(
        row.profile,
        last_name=profile.last_name,
        first_name=profile.first_name,
        middle_name=profile.middle_name,
        position=profile.position,
    )


# --- consent -------------------------------------------------------------------------------


def consent_to_entity(row: ConsentModel) -> Consent:
    return Consent(
        id=row.id,
        account_id=row.account_id,
        type=cast(ConsentType, row.type),
        given_at=aware(row.given_at),
        valid_until=_aware_or_none(row.valid_until),
        revoked_at=_aware_or_none(row.revoked_at),
        text_version=row.text_version,
        ip=row.ip,
        user_agent=row.user_agent,
        organization_id=row.organization_id,
        revoked_by=row.revoked_by,
    )


def consent_to_row(consent: Consent) -> ConsentModel:
    return ConsentModel(
        id=consent.id,
        account_id=consent.account_id,
        organization_id=consent.organization_id,
        type=consent.type,
        given_at=consent.given_at,
        valid_until=consent.valid_until,
        revoked_at=consent.revoked_at,
        revoked_by=consent.revoked_by,
        text_version=consent.text_version,
        ip=consent.ip,
        user_agent=consent.user_agent,
    )
