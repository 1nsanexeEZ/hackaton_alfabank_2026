"""The loan contract: shown once the offer is accepted, then signed."""

from typing import cast
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ConflictError, ValidationError
from src.core.uow import UnitOfWork
from src.modules.applications.application.dto.views import (
    ContractDTO,
    ContractSignerDTO,
    SignatureDTO,
    SignResultDTO,
)
from src.modules.applications.application.interfaces.edo import EdoClient
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.mappers.dto import contract_dto, snapshot_to_dto
from src.modules.applications.application.use_cases.common import get_writable, publish, view
from src.modules.applications.domain.enums import ApplicationStatus
from src.modules.applications.domain.value_objects import Actor
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.identity.facade import IdentityFacade
from src.modules.products.facade import ProductsFacade, Repayment

# The contract exists once the client accepted the offer.
CONTRACT_STATUSES = frozenset(
    {ApplicationStatus.SIGNING, ApplicationStatus.SIGNED, ApplicationStatus.DISBURSED}
)


class GetContractUseCase:
    """The loan contract to show before signing: borrower, terms, schedule
    and who may sign."""

    def __init__(
        self,
        repository: ApplicationRepository,
        clients: ClientsFacade,
        products: ProductsFacade,
        identity: IdentityFacade,
        edo: EdoClient,
    ) -> None:
        self._repository = repository
        self._clients = clients
        self._products = products
        self._identity = identity
        self._edo = edo

    async def execute(self, access: AccessContext, application_id: UUID) -> ContractDTO:
        application = await self._repository.get(application_id, access)
        if application.status not in CONTRACT_STATUSES or application.offer is None:
            raise ConflictError(
                "The contract appears once the offer is accepted",
                details={"code": "contract_not_ready"},
            )
        offer = application.offer
        borrower = (
            snapshot_to_dto(application.org_snapshot)
            if application.org_snapshot is not None
            else await self._clients.get_snapshot(application.organization_id)
        )
        schedule = self._products.calculate_payment(
            offer.amount.amount, offer.term_months, offer.rate, cast(Repayment, offer.schedule_type)
        )
        signers = await self._signers(application.organization_id, borrower.head_name)
        return contract_dto(
            application, offer, borrower, tuple(signers), schedule, self._edo.simulated
        )

    async def _signers(
        self, organization_id: UUID, head_name: str | None
    ) -> list[ContractSignerDTO]:
        """Members who hold the right to sign today. The head by the registry
        signs by law; anyone else holding the right has a power of attorney."""
        signers = []
        for account_id in await self._clients.list_members(organization_id, OrgPermission.SIGN):
            account = await self._identity.get_account(account_id)
            if account is None:
                continue
            parts = (account.last_name, account.first_name, account.middle_name)
            name = " ".join(p for p in parts if p)
            by_registry = head_name is not None and _same_person(name, head_name)
            signers.append(
                ContractSignerDTO(
                    account_id, name, "registry" if by_registry else "power_of_attorney"
                )
            )
        return signers


class SignApplicationUseCase:
    """Signing is a legally meaningful act: the right to sign inside the
    company plus the password once more (a stolen session is not enough),
    and exactly the offer the client saw in the contract."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        identity: IdentityFacade,
        edo: EdoClient,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._identity = identity
        self._edo = edo
        self._clock = clock

    async def execute(
        self,
        access: AccessContext,
        application_id: UUID,
        password: str,
        offer_hash: str,
        ip: str | None,
        user_agent: str | None,
    ) -> SignResultDTO:
        application = await get_writable(
            self._repository, self._clients, access, application_id, OrgPermission.SIGN
        )
        if not await self._identity.verify_password(access.user_id, password):
            raise ValidationError("Wrong password", details={"code": "invalid_password"})
        signature = application.sign(Actor.client(access.user_id), self._clock.now(), offer_hash)
        receipt = await self._edo.sign(
            application.id, str(application.number), signature.offer_hash, access.user_id
        )
        async with self._uow:
            await self._repository.save(application)
            # where it was signed from, next to the signature
            await self._repository.record_signature_details(
                application.id, ip, user_agent, receipt.document_id
            )
            await publish(application, self._outbox)
            await self._uow.commit()
        return SignResultDTO(
            application=await view(self._clients, access, application),
            signature=SignatureDTO(
                signed_at=signature.signed_at,
                offer_hash=signature.offer_hash,
                edo_document_id=receipt.document_id,
                simulated=receipt.simulated,
            ),
        )


def _same_person(name: str, registry_name: str) -> bool:
    """The comparison clients makes with the registry head: case, ё and
    spacing do not matter."""

    def normalized(value: str) -> str:
        return " ".join(value.lower().replace("ё", "е").split())

    return normalized(name) == normalized(registry_name)
