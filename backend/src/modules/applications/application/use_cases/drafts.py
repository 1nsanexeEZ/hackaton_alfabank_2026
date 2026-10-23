"""A draft: created for a company and a product, then autosaved by the client."""

from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.uow import UnitOfWork
from src.modules.applications.application.dto.applications import CollateralDTO
from src.modules.applications.application.dto.common import UNSET
from src.modules.applications.application.dto.drafts import DraftChangesDTO, DraftRequestDTO
from src.modules.applications.application.dto.views import ApplicationViewDTO
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.mappers.dto import (
    collateral_declaration,
    loan_request,
    terms_from_dto,
)
from src.modules.applications.application.use_cases.common import (
    get_writable,
    publish,
    save,
    take_profile_consents,
    view,
)
from src.modules.applications.domain.application import CreditApplication
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.identity.facade import IdentityFacade
from src.modules.products.facade import ProductsFacade


class CreateDraftUseCase:
    """Draft for a company and a product; requisites come from the bank's data, the
    consents already given — from the profile."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        products: ProductsFacade,
        identity: IdentityFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._products = products
        self._identity = identity
        self._clock = clock

    async def execute(
        self, access: AccessContext, organization_id: UUID, product_code: str
    ) -> ApplicationViewDTO:
        if access.organization_ids is not None and organization_id not in access.organization_ids:
            raise NotFoundError("Organization not found")
        await self._clients.ensure_can(
            access.user_id, organization_id, OrgPermission.SUBMIT_APPLICATION
        )
        existing = await self._repository.find_active(organization_id, product_code)
        if existing is not None:
            raise ConflictError(
                "The company already has an active application for this product",
                details={"code": "duplicate_active", "application_id": str(existing)},
            )
        eligibility = await self._products.check_eligibility(product_code, organization_id)
        if not eligibility.eligible:
            raise ValidationError(
                "The company does not fit the product",
                details={
                    "code": "not_eligible",
                    "reasons": [
                        {"code": r.code, "message": r.message}
                        for r in eligibility.reasons
                        if not r.passed
                    ],
                },
            )
        terms = terms_from_dto(await self._products.get_terms_snapshot(product_code))
        now = self._clock.now()
        application = CreditApplication.create_draft(
            id=uuid4(),
            number=await self._repository.next_number(now.year),
            organization_id=organization_id,
            applicant_account_id=access.user_id,
            product_terms=terms,
            now=now,
        )
        await take_profile_consents(self._identity, application, access.user_id, now)
        async with self._uow:
            await self._repository.add(application)
            await publish(application, self._outbox)
            await self._uow.commit()
        return await view(self._clients, access, application)


class UpdateDraftUseCase:
    """Autosave of a draft: only what the client sent changes."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._clock = clock

    async def execute(
        self, access: AccessContext, application_id: UUID, changes: DraftChangesDTO
    ) -> ApplicationViewDTO:
        # The values are checked before the application is read: a bad value
        # is 422 even for an application the caller may not change.
        request = (
            loan_request(changes.request) if isinstance(changes.request, DraftRequestDTO) else None
        )
        collateral = (
            collateral_declaration(changes.collateral)
            if isinstance(changes.collateral, CollateralDTO)
            else None
        )
        application = await get_writable(
            self._repository,
            self._clients,
            access,
            application_id,
            OrgPermission.SUBMIT_APPLICATION,
        )
        application.check_version(changes.version)
        now = self._clock.now()
        if request is not None:
            application.change_request(request, now)
        if changes.product_fields is not UNSET and changes.product_fields is not None:
            application.change_product_fields(changes.product_fields, now)
        if changes.collateral is not UNSET:
            application.change_collateral(collateral, now)
        if changes.consents is not UNSET:
            consents = changes.consents
            application.set_consents(
                personal_data=consents.personal_data if consents else False,
                credit_bureau=consents.credit_bureau if consents else False,
                account_id=access.user_id,
                now=now,
                automated_decision=consents.automated_decision if consents else False,
            )
        await save(self._uow, self._repository, self._outbox, application)
        return await view(self._clients, access, application)
