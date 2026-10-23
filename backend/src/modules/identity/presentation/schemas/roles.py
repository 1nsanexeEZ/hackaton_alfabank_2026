from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.modules.identity.application.dto.roles import CreateRoleDTO, UpdateRoleDTO


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: list[Permissions] = Field(default_factory=list)
    policies: dict[Permissions, list[Policies]] = Field(default_factory=dict)

    def to_dto(self) -> CreateRoleDTO:
        return CreateRoleDTO(
            name=self.name,
            description=self.description,
            permissions=self.permissions,
            policies=self.policies,
        )


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[Permissions] | None = None
    policies: dict[Permissions, list[Policies]] | None = None

    def to_dto(self) -> UpdateRoleDTO:
        return UpdateRoleDTO(
            name=self.name,
            description=self.description,
            permissions=self.permissions,
            policies=self.policies,
        )


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    permissions: list[str]
    policies: dict[str, list[str]]
    created_at: datetime
    updated_at: datetime


class RoleShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
