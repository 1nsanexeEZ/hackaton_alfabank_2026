"""Consents a representative gives for a company (credit_bureau_company), before any
application: the application takes them from here. The rights inside the company are
checked by clients: viewing needs `view`, giving and revoking — `submit_application`,
as the consents in an application draft."""

from uuid import UUID

from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.identity.application.dto.consents import ConsentRecordDTO, GiveConsentsDTO
from src.modules.identity.application.interfaces.repositories import (
    AccountRepository,
    ConsentRepository,
)
from src.modules.identity.application.use_cases.me import get_current_account
from src.modules.identity.domain.entities import Consent
from src.modules.identity.domain.enums import ConsentType


class ListOrganizationConsentsUseCase:
    def __init__(
        self,
        accounts: AccountRepository,
        consents: ConsentRepository,
        clients: ClientsFacade,
        clock: Clock,
    ) -> None:
        self._accounts = accounts
        self._consents = consents
        self._clients = clients
        self._clock = clock

    async def execute(self, user_id: UUID, organization_id: UUID) -> list[ConsentRecordDTO]:
        """In force and the history, by any representative, newest first."""
        await get_current_account(self._accounts, user_id)
        await self._clients.ensure_can(user_id, organization_id, OrgPermission.VIEW)
        now = self._clock.now()
        return [
            ConsentRecordDTO.from_entity(consent, now)
            for consent in await self._consents.list_for_organization(organization_id)
        ]


class GiveOrganizationConsentsUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        consents: ConsentRepository,
        clients: ClientsFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._consents = consents
        self._clients = clients
        self._clock = clock

    async def execute(
        self, user_id: UUID, organization_id: UUID, data: GiveConsentsDTO
    ) -> list[ConsentRecordDTO]:
        """Each type is a new consent of the company, kept with who gave it, the request's
        IP and User-Agent."""
        async with self._uow:
            await get_current_account(self._accounts, user_id)
            await self._clients.ensure_can(
                user_id, organization_id, OrgPermission.SUBMIT_APPLICATION
            )
            now = self._clock.now()
            given = [
                Consent.give(
                    user_id,
                    type,
                    now,
                    ip=data.ip,
                    user_agent=data.user_agent,
                    organization_id=organization_id,
                )
                for type in dict.fromkeys(data.types)
            ]
            for consent in given:
                await self._consents.add(consent)
            await self._uow.commit()
        return [ConsentRecordDTO.from_entity(consent, now) for consent in given]


class RevokeOrganizationConsentUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        consents: ConsentRepository,
        clients: ClientsFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._consents = consents
        self._clients = clients
        self._clock = clock

    async def execute(self, user_id: UUID, organization_id: UUID, type: ConsentType) -> None:
        """Closes the company's consents in force, whoever gave them. Idempotent."""
        async with self._uow:
            await get_current_account(self._accounts, user_id)
            await self._clients.ensure_can(
                user_id, organization_id, OrgPermission.SUBMIT_APPLICATION
            )
            now = self._clock.now()
            in_force = [
                consent
                for consent in await self._consents.list_not_revoked_for_organization(
                    organization_id, type
                )
                if consent.is_active(now)
            ]
            if not in_force:
                return
            for consent in in_force:
                consent.revoke(now, by=user_id)
                await self._consents.save(consent)
            await self._uow.commit()
