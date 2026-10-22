"""Use cases of the client side of an application.

Access is checked twice, on purpose:
- rows: the repository applies the caller's policies (`org_member` — only
  applications of the caller's companies; a stranger gets 404);
- rights inside the company: `clients.ensure_can(...)` — who may submit,
  who may sign (an accountant without a power of attorney may not).
Bank staff read without a company check; writing is not given to them.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import (
    ConflictError,
    InfrastructureError,
    NotFoundError,
    ValidationError,
)
from src.core.messaging.outbox import OutboxWriter
from src.modules.applications.application.ports import (
    ApplicationRepository,
    DocumentStorage,
    EdoClient,
    PresignedUpload,
)
from src.modules.applications.application.translate import (
    snapshot_from_dto,
    terms_from_dto,
    to_contract,
)
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.entities import Document
from src.modules.applications.domain.value_objects import (
    Actor,
    CollateralDeclaration,
    LoanRequest,
    Signature,
    Violation,
)
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO, OrgPermission
from src.modules.identity.facade import IdentityFacade
from src.modules.products.facade import ProductsFacade

UPLOAD_URL_TTL_SECONDS = 300
DOWNLOAD_URL_TTL_SECONDS = 60


@dataclass(frozen=True)
class ApplicationView:
    application: CreditApplication
    # Live company data for a draft (prefilled requisites); after submission
    # the frozen snapshot inside the application is the source.
    organization: OrganizationSnapshotDTO | None
    my_permissions: frozenset[str]


@dataclass(frozen=True)
class DocumentUpload:
    document: Document
    upload: PresignedUpload


@dataclass(frozen=True)
class SignResult:
    view: ApplicationView
    signature: Signature
    edo_document_id: str
    simulated: bool


@dataclass(frozen=True)
class DraftChanges:
    """PATCH body; `fields_set` tells "not sent" from "sent as null"."""

    version: int
    fields_set: frozenset[str]
    request: LoanRequest | None = None
    product_fields: dict[str, Any] | None = None
    collateral: CollateralDeclaration | None = None
    personal_data_consent: bool | None = None
    credit_bureau_consent: bool | None = None


class ApplicationService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: ApplicationRepository,
        outbox: OutboxWriter,
        storage: DocumentStorage,
        edo: EdoClient,
        clients: ClientsFacade,
        products: ProductsFacade,
        identity: IdentityFacade,
        clock: Clock,
    ) -> None:
        self._session = session
        self._repository = repository
        self._outbox = outbox
        self._storage = storage
        self._edo = edo
        self._clients = clients
        self._products = products
        self._identity = identity
        self._clock = clock

    # --- reading ------------------------------------------------------------

    async def get(self, access: AccessContext, application_id: UUID) -> ApplicationView:
        application = await self._repository.get(application_id, access)
        return await self._view(access, application)

    async def list_applications(
        self,
        access: AccessContext,
        organization_id: UUID | None,
        statuses: Sequence[str] | None,
        limit: int,
        offset: int,
    ) -> list[CreditApplication]:
        return await self._repository.search(access, organization_id, statuses, limit, offset)

    async def completeness(self, access: AccessContext, application_id: UUID) -> list[Violation]:
        application = await self._repository.get(application_id, access)
        legal_form = await self._legal_form(application)
        other = await self._repository.find_active(
            application.organization_id, application.product_code, exclude_id=application.id
        )
        return application.check_ready(legal_form, has_other_active=other is not None)

    async def download_url(
        self, access: AccessContext, application_id: UUID, document_id: UUID
    ) -> str:
        application = await self._repository.get(application_id, access)
        document = application.document(document_id)
        if not document.is_uploaded:
            raise NotFoundError("Document is not uploaded yet")
        return await self._storage.presign_download(
            document.s3_key, document.filename, DOWNLOAD_URL_TTL_SECONDS
        )

    # --- draft --------------------------------------------------------------

    async def create_draft(
        self, access: AccessContext, organization_id: UUID, product_code: str
    ) -> ApplicationView:
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
        await self._persist(application, new=True)
        return await self._view(access, application)

    async def update_draft(
        self, access: AccessContext, application_id: UUID, changes: DraftChanges
    ) -> ApplicationView:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        application.check_version(changes.version)
        now = self._clock.now()
        if "request" in changes.fields_set and changes.request is not None:
            application.change_request(changes.request, now)
        if "product_fields" in changes.fields_set and changes.product_fields is not None:
            application.change_product_fields(changes.product_fields, now)
        if "collateral" in changes.fields_set:
            application.change_collateral(changes.collateral, now)
        if "consents" in changes.fields_set:
            application.set_consents(
                personal_data=bool(changes.personal_data_consent),
                credit_bureau=bool(changes.credit_bureau_consent),
                account_id=access.user_id,
                now=now,
            )
        await self._save(application)
        return await self._view(access, application)

    # --- documents ----------------------------------------------------------

    async def request_upload(
        self,
        access: AccessContext,
        application_id: UUID,
        document_type: str,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> DocumentUpload:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        document = application.add_document(
            document_id=uuid4(),
            document_type=document_type,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            uploaded_by=access.user_id,
            now=self._clock.now(),
        )
        upload = await self._storage.presign_upload(
            document.s3_key, content_type, size_bytes, UPLOAD_URL_TTL_SECONDS
        )
        await self._save(application)
        return DocumentUpload(document, upload)

    async def confirm_upload(
        self, access: AccessContext, application_id: UUID, document_id: UUID
    ) -> Document:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        document = application.document(document_id)
        stored = await self._storage.head(document.s3_key)
        if stored is None:
            raise ValidationError(
                "The file has not reached the storage yet", details={"code": "upload_missing"}
            )
        application.confirm_document(
            document_id, stored.size, stored.content_type, self._clock.now()
        )
        await self._save(application)
        return document

    async def delete_document(
        self, access: AccessContext, application_id: UUID, document_id: UUID
    ) -> None:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        document = application.remove_document(document_id, self._clock.now())
        await self._save(application)
        try:
            await self._storage.delete(document.s3_key)
        except InfrastructureError:
            pass  # an orphan object in a private bucket is harmless

    # --- submission and answers -----------------------------------------------

    async def submit(self, access: AccessContext, application_id: UUID) -> ApplicationView:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        now = self._clock.now()
        snapshot = await self._clients.get_snapshot(application.organization_id)
        other = await self._repository.find_active(
            application.organization_id, application.product_code, exclude_id=application.id
        )
        application.submit(
            snapshot_from_dto(snapshot, now),
            actor=Actor.client(access.user_id),
            has_other_active=other is not None,
            now=now,
        )
        await self._save(application)
        return await self._view(access, application)

    async def answer_info_request(
        self, access: AccessContext, application_id: UUID, info_request_id: UUID
    ) -> ApplicationView:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        application.answer_info_request(
            info_request_id, Actor.client(access.user_id), self._clock.now()
        )
        await self._save(application)
        return await self._view(access, application)

    async def accept_offer(self, access: AccessContext, application_id: UUID) -> ApplicationView:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        application.accept_offer(Actor.client(access.user_id), self._clock.now())
        await self._save(application)
        return await self._view(access, application)

    async def decline_offer(
        self, access: AccessContext, application_id: UUID, reason: str | None
    ) -> ApplicationView:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        application.decline_offer(Actor.client(access.user_id), self._clock.now(), reason)
        await self._save(application)
        return await self._view(access, application)

    async def sign(
        self,
        access: AccessContext,
        application_id: UUID,
        password: str,
        ip: str | None,
        user_agent: str | None,
    ) -> SignResult:
        """Signing is a legally meaningful act: the right to sign inside the
        company plus the password once more (a stolen session is not enough)."""
        application = await self._writable(access, application_id, OrgPermission.SIGN)
        if not await self._identity.verify_password(access.user_id, password):
            raise ValidationError("Wrong password", details={"code": "invalid_password"})
        signature = application.sign(Actor.client(access.user_id), self._clock.now())
        receipt = await self._edo.sign(
            application.id, str(application.number), signature.offer_hash, access.user_id
        )

        async def remember_where_from() -> None:
            await self._repository.record_signature_details(
                application.id, ip, user_agent, receipt.document_id
            )

        await self._persist(application, before_commit=remember_where_from)
        return SignResult(
            await self._view(access, application), signature, receipt.document_id, receipt.simulated
        )

    async def cancel(
        self, access: AccessContext, application_id: UUID, reason: str | None
    ) -> ApplicationView:
        application = await self._writable(access, application_id, OrgPermission.SUBMIT_APPLICATION)
        application.cancel(Actor.client(access.user_id), self._clock.now(), reason)
        await self._save(application)
        return await self._view(access, application)

    # --- internals ----------------------------------------------------------

    async def _writable(
        self, access: AccessContext, application_id: UUID, permission: OrgPermission
    ) -> CreditApplication:
        application = await self._repository.get(application_id, access)
        await self._clients.ensure_can(access.user_id, application.organization_id, permission)
        return application

    async def _save(self, application: CreditApplication) -> None:
        await self._persist(application)

    async def _persist(
        self,
        application: CreditApplication,
        *,
        new: bool = False,
        before_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """The aggregate, its history and the outgoing events — one transaction."""
        try:
            if new:
                await self._repository.add(application)
            else:
                await self._repository.save(application)
            if before_commit is not None:
                await before_commit()
            for event in application.pull_events():
                await self._outbox.add(
                    to_contract(event), key=application.id, correlation_id=application.id
                )
            await self._session.commit()
        except StaleDataError:
            await self._session.rollback()
            raise ConflictError(
                "Application was changed by someone else, reload it",
                details={"code": "version_conflict"},
            ) from None
        except IntegrityError:
            await self._session.rollback()
            raise ConflictError(
                "The company already has an active application for this product",
                details={"code": "duplicate_active"},
            ) from None

    async def _view(self, access: AccessContext, application: CreditApplication) -> ApplicationView:
        organization: OrganizationSnapshotDTO | None = None
        permissions: frozenset[str] = frozenset()
        if access.organization_ids is not None:  # a client, not bank staff
            permissions = await self._clients.get_member_permissions(
                access.user_id, application.organization_id
            )
        if application.org_snapshot is None:
            organization = await self._clients.get_snapshot(application.organization_id)
        return ApplicationView(application, organization, permissions)

    async def _legal_form(self, application: CreditApplication) -> str:
        if application.org_snapshot is not None:
            return application.org_snapshot.legal_form
        return (await self._clients.get_snapshot(application.organization_id)).legal_form
