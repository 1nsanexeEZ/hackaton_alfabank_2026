from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.uow import UnitOfWork
from src.modules.identity.application.dto.roles import CreateRoleDTO, RoleDTO, UpdateRoleDTO
from src.modules.identity.application.interfaces.repositories import RoleRepository
from src.modules.identity.domain.entities import Role
from src.modules.identity.domain.exceptions import (
    RoleAlreadyExistsError,
    RoleInUseError,
    RoleNotFoundError,
)


async def _get_role(roles: RoleRepository, access: AccessContext, role_id: UUID) -> Role:
    role = await roles.get(access, role_id)
    if role is None:
        raise RoleNotFoundError()
    return role


class ListRolesUseCase:
    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def execute(self, access: AccessContext) -> list[RoleDTO]:
        return [RoleDTO.from_entity(role) for role in await self._roles.list(access)]


class GetRoleUseCase:
    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def execute(self, access: AccessContext, role_id: UUID) -> RoleDTO:
        return RoleDTO.from_entity(await _get_role(self._roles, access, role_id))


class CreateRoleUseCase:
    def __init__(self, uow: UnitOfWork, roles: RoleRepository) -> None:
        self._uow = uow
        self._roles = roles

    async def execute(self, data: CreateRoleDTO) -> RoleDTO:
        async with self._uow:
            if await self._roles.get_by_name(data.name) is not None:
                raise RoleAlreadyExistsError(data.name)
            role = Role.create(data.name, data.description, data.permissions, data.policies)
            await self._roles.add(role)
            await self._uow.commit()
        return RoleDTO.from_entity(role)


class UpdateRoleUseCase:
    """Accounts get the new rights with their next token."""

    def __init__(self, uow: UnitOfWork, roles: RoleRepository) -> None:
        self._uow = uow
        self._roles = roles

    async def execute(self, access: AccessContext, role_id: UUID, data: UpdateRoleDTO) -> RoleDTO:
        async with self._uow:
            role = await _get_role(self._roles, access, role_id)
            if data.name is not None and data.name != role.name:
                if await self._roles.get_by_name(data.name) is not None:
                    raise RoleAlreadyExistsError(data.name)
                role.name = data.name
            if data.description is not None:
                role.description = data.description
            if data.permissions is not None or data.policies is not None:
                role.change_rules(data.permissions, data.policies)
            await self._roles.save(role)
            await self._uow.commit()
        return RoleDTO.from_entity(role)


class DeleteRoleUseCase:
    def __init__(self, uow: UnitOfWork, roles: RoleRepository) -> None:
        self._uow = uow
        self._roles = roles

    async def execute(self, access: AccessContext, role_id: UUID) -> None:
        async with self._uow:
            role = await _get_role(self._roles, access, role_id)
            if await self._roles.is_in_use(role.id):
                raise RoleInUseError()
            await self._roles.delete(role)
            await self._uow.commit()
