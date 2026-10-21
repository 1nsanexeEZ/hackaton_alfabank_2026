from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias
from uuid import UUID

from sqlalchemy import Delete, Select, Update

from src.core.access.access_context import AccessContext
from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.core.infrastructure.database.mixins import DeletedMixin, OwnableMixin

Statement: TypeAlias = Select[*tuple[Any, ...]] | Update | Delete


def apply_policy(stmt: Statement, model: type[Any], policy: Policies, user_id: UUID) -> Statement:
    """Narrow a single statement with one row-level policy.

    Raises ValueError if the model can't support the policy — a policy that
    cannot be enforced is an access hole, so we fail loud instead of silently
    returning an unrestricted query.
    """
    if policy is Policies.NOT_DELETED:
        if not issubclass(model, DeletedMixin):
            raise ValueError(f"{model.__name__} does not support policy {policy.value!r}")
        return stmt.where(model.entity_is_not_deleted())
    if policy is Policies.OWN_ONLY:
        if not issubclass(model, OwnableMixin):
            raise ValueError(f"{model.__name__} does not support policy {policy.value!r}")
        return stmt.where(model.user_is_owner(user_id))
    raise ValueError(f"Unknown policy: {policy!r}")


def apply_policies(
    stmt: Statement,
    model: type[Any],
    permission: Permissions,
    granted_permissions: Sequence[str],
    policies: Mapping[str, Sequence[str]],
    user_id: UUID,
) -> Statement:
    """Apply every row-level policy attached to `permission` for the current user.

    `granted_permissions` / `policies` come straight from the token
    (OpenSubTokenDTO). Does NOT check whether the user holds `permission` —
    that already happened when the AccessContext was built (see
    src.core.access.dependencies.get_access_context_for).
    Admins are never row-restricted.
    """
    if Permissions.ADMIN.value in granted_permissions:
        return stmt
    for raw in policies.get(permission.value, ()):
        stmt = apply_policy(stmt, model, Policies(raw), user_id)
    return stmt


def apply_access_context(stmt: Statement, model: type[Any], access: AccessContext) -> Statement:
    """Shortcut for repositories that receive a ready AccessContext."""
    return apply_policies(
        stmt,
        model,
        access.permission,
        access.granted_permissions,
        access.policies,
        access.user_id,
    )
