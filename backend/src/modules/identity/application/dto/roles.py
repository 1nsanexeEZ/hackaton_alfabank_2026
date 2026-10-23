from dataclasses import dataclass, field
from datetime import datetime
from typing import Self
from uuid import UUID

from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.modules.identity.application.dto.common import stored
from src.modules.identity.domain.entities import Role


@dataclass(frozen=True, slots=True)
class RoleDTO:
    id: UUID
    name: str
    description: str
    permissions: list[str]
    policies: dict[str, list[str]]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, role: Role) -> Self:
        return cls(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=list(role.permissions),
            policies={k: list(v) for k, v in role.policies.items()},
            created_at=stored(role.created_at),
            updated_at=stored(role.updated_at),
        )


@dataclass(frozen=True, slots=True)
class CreateRoleDTO:
    name: str
    description: str = ""
    permissions: list[Permissions] = field(default_factory=list)
    policies: dict[Permissions, list[Policies]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateRoleDTO:
    """None keeps the current value."""

    name: str | None = None
    description: str | None = None
    permissions: list[Permissions] | None = None
    policies: dict[Permissions, list[Policies]] | None = None
