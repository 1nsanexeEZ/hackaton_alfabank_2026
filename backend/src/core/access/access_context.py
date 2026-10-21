from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from src.core.access.permissions import Permissions


@dataclass(frozen=True)
class AccessContext:
    user_id: UUID
    permission: Permissions
    granted_permissions: Sequence[str] = field(default_factory=tuple)
    policies: Mapping[str, Sequence[str]] = field(default_factory=dict)
    # Filled only when the permission carries the `org_member` policy:
    # organizations the user is a member of (resolved through the clients module).
    organization_ids: frozenset[UUID] | None = None
