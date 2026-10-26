"""Members of a company and their rights: changed by a member with
`manage_members` or by the bank, a power of attorney — by the head confirmed
by the registry."""

from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ValidationError
from src.core.uow import UnitOfWork
from src.modules.clients.application.dto.members import GrantPowerOfAttorneyDTO, MemberDTO
from src.modules.clients.application.interfaces.outbox import EventOutbox
from src.modules.clients.application.interfaces.repositories import OrganizationRepository
from src.modules.clients.application.use_cases.common import (
    actor_of,
    get_organization,
    get_to_change,
    person_of,
    save_with_events,
)
from src.modules.clients.domain.enums import MemberRole, OrgPermission
from src.modules.clients.domain.rights import PowerOfAttorney
from src.modules.identity.facade import IdentityFacade


class ListMembersUseCase:
    def __init__(
        self, organizations: OrganizationRepository, identity: IdentityFacade, clock: Clock
    ) -> None:
        self._organizations = organizations
        self._identity = identity
        self._clock = clock

    async def execute(self, access: AccessContext, organization_id: UUID) -> list[MemberDTO]:
        now = self._clock.now()
        org = await get_organization(self._organizations, organization_id, access)
        return [
            MemberDTO.of(m, await self._identity.get_account(m.account_id), now)
            for m in org.members
        ]


class AddMemberUseCase:
    """The account must exist already: there is no registration."""

    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        identity: IdentityFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._outbox = outbox
        self._identity = identity
        self._clock = clock

    async def execute(
        self, access: AccessContext, organization_id: UUID, login: str, role: MemberRole
    ) -> MemberDTO:
        async with self._uow:
            org = await get_to_change(self._organizations, access, organization_id)
            # Rights first: a member without manage_members learns nothing about logins.
            actor = actor_of(access)
            if not actor.is_bank:
                org.ensure_can(access.user_id, OrgPermission.MANAGE_MEMBERS, self._clock.now())
            account = await self._identity.find_by_login(login.strip())
            if account is None:
                raise ValidationError(
                    "No account with this login",
                    details={"field": "login", "code": "account_not_found"},
                )
            member = org.add_member(
                actor, account.id, role, self._clock.now(), person=person_of(account)
            )
            await save_with_events(self._organizations, self._outbox, org)
            await self._uow.commit()
        return MemberDTO.of(member, account, self._clock.now())


class ChangeMemberRoleUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._outbox = outbox
        self._clock = clock

    async def execute(
        self, access: AccessContext, organization_id: UUID, account_id: UUID, role: MemberRole
    ) -> MemberDTO:
        async with self._uow:
            org = await get_to_change(self._organizations, access, organization_id)
            member = org.change_role(actor_of(access), account_id, role, self._clock.now())
            await save_with_events(self._organizations, self._outbox, org)
            await self._uow.commit()
        return MemberDTO.of(member, None, self._clock.now())


class RemoveMemberUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._outbox = outbox
        self._clock = clock

    async def execute(self, access: AccessContext, organization_id: UUID, account_id: UUID) -> None:
        async with self._uow:
            org = await get_to_change(self._organizations, access, organization_id)
            org.remove_member(actor_of(access), account_id, self._clock.now())
            await save_with_events(self._organizations, self._outbox, org)
            await self._uow.commit()


class GrantPowerOfAttorneyUseCase:
    """Issued by the head confirmed by the registry; replaces the previous one."""

    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._outbox = outbox
        self._clock = clock

    async def execute(
        self,
        access: AccessContext,
        organization_id: UUID,
        account_id: UUID,
        data: GrantPowerOfAttorneyDTO,
    ) -> MemberDTO:
        power_of_attorney = PowerOfAttorney.issue(
            number=data.number,
            issued_at=data.issued_at,
            valid_until=data.valid_until,
            scope=frozenset(OrgPermission(p) for p in data.scope),
        )
        async with self._uow:
            org = await get_to_change(self._organizations, access, organization_id)
            member = org.grant_power_of_attorney(
                actor_of(access), account_id, power_of_attorney, self._clock.now()
            )
            await save_with_events(self._organizations, self._outbox, org)
            await self._uow.commit()
        return MemberDTO.of(member, None, self._clock.now())


class RevokePowerOfAttorneyUseCase:
    """By the head confirmed by the registry or the bank; the rights it gave end at once."""

    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._outbox = outbox
        self._clock = clock

    async def execute(
        self, access: AccessContext, organization_id: UUID, account_id: UUID
    ) -> MemberDTO:
        async with self._uow:
            org = await get_to_change(self._organizations, access, organization_id)
            member = org.revoke_power_of_attorney(actor_of(access), account_id, self._clock.now())
            await save_with_events(self._organizations, self._outbox, org)
            await self._uow.commit()
        return MemberDTO.of(member, None, self._clock.now())
