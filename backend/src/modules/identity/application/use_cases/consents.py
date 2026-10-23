"""Consents a person gives for themselves (not for the company): history is kept,
a new consent is a new record, a revocation closes every consent of the type in force."""

from uuid import UUID

from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.identity.application.dto.consents import ConsentRecordDTO, GiveConsentsDTO
from src.modules.identity.application.interfaces.repositories import (
    AccountRepository,
    ConsentRepository,
)
from src.modules.identity.application.use_cases.me import get_current_account
from src.modules.identity.domain.entities import Consent
from src.modules.identity.domain.enums import ConsentType


class ListMyConsentsUseCase:
    def __init__(
        self, accounts: AccountRepository, consents: ConsentRepository, clock: Clock
    ) -> None:
        self._accounts = accounts
        self._consents = consents
        self._clock = clock

    async def execute(self, user_id: UUID) -> list[ConsentRecordDTO]:
        """In force and the history, newest first."""
        await get_current_account(self._accounts, user_id)
        now = self._clock.now()
        return [
            ConsentRecordDTO.from_entity(consent, now)
            for consent in await self._consents.list_for(user_id)
        ]


class GiveConsentsUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        consents: ConsentRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._consents = consents
        self._clock = clock

    async def execute(self, user_id: UUID, data: GiveConsentsDTO) -> list[ConsentRecordDTO]:
        """Each type is a new consent, kept with the request's IP and User-Agent."""
        async with self._uow:
            await get_current_account(self._accounts, user_id)
            now = self._clock.now()
            given = [
                Consent.give(user_id, type, now, ip=data.ip, user_agent=data.user_agent)
                for type in dict.fromkeys(data.types)
            ]
            for consent in given:
                await self._consents.add(consent)
            await self._uow.commit()
        return [ConsentRecordDTO.from_entity(consent, now) for consent in given]


class RevokeConsentUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        consents: ConsentRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._consents = consents
        self._clock = clock

    async def execute(self, user_id: UUID, type: ConsentType) -> None:
        """Idempotent: nothing in force — nothing changes."""
        async with self._uow:
            await get_current_account(self._accounts, user_id)
            now = self._clock.now()
            in_force = [
                consent
                for consent in await self._consents.list_not_revoked(user_id, type)
                if consent.is_active(now)
            ]
            if not in_force:
                return
            for consent in in_force:
                consent.revoke(now)
                await self._consents.save(consent)
            await self._uow.commit()
