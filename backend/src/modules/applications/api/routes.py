from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from src.core.domain import Money
from src.modules.applications.api import presenters
from src.modules.applications.api.dependencies import (
    CanCreate,
    CanRead,
    CanUpdate,
    Service,
    client_ip,
)
from src.modules.applications.api.schemas import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationOut,
    ApplicationUpdate,
    CompletenessOut,
    DocumentOut,
    DocumentUploadIn,
    DocumentUploadOut,
    DownloadOut,
    ReasonIn,
    SignatureOut,
    SignIn,
    SignOut,
    ViolationOut,
)
from src.modules.applications.application.service import DraftChanges
from src.modules.applications.domain.value_objects import CollateralDeclaration, LoanRequest

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_draft(
    data: ApplicationCreate, access: CanCreate, service: Service
) -> ApplicationOut:
    """Draft for a company and a product; requisites come from the bank's data."""
    view = await service.create_draft(access, data.organization_id, data.product_code)
    return presenters.application(view)


@router.get("", response_model=list[ApplicationListItem])
async def list_applications(
    access: CanRead,
    service: Service,
    organization_id: UUID | None = None,
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ApplicationListItem]:
    applications = await service.list_applications(
        access, organization_id, status_filter, limit, offset
    )
    return [presenters.list_item(application) for application in applications]


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: UUID, access: CanRead, service: Service
) -> ApplicationOut:
    return presenters.application(await service.get(access, application_id))


@router.patch("/{application_id}", response_model=ApplicationOut)
async def update_draft(
    application_id: UUID, data: ApplicationUpdate, access: CanUpdate, service: Service
) -> ApplicationOut:
    request = data.request
    collateral = data.collateral
    changes = DraftChanges(
        version=data.version,
        fields_set=frozenset(data.model_fields_set),
        request=LoanRequest(
            amount=Money.of(request.amount) if request.amount is not None else None,
            term_months=request.term_months,
            purpose=request.purpose,
            purpose_comment=request.purpose_comment,
        )
        if request
        else None,
        product_fields=data.product_fields,
        collateral=CollateralDeclaration(
            type=collateral.type,
            description=collateral.description,
            declared_value=Money.of(collateral.declared_value),
            owner=collateral.owner,
        )
        if collateral
        else None,
        personal_data_consent=data.consents.personal_data if data.consents else None,
        credit_bureau_consent=data.consents.credit_bureau if data.consents else None,
    )
    return presenters.application(await service.update_draft(access, application_id, changes))


@router.get("/{application_id}/completeness", response_model=CompletenessOut)
async def completeness(application_id: UUID, access: CanRead, service: Service) -> CompletenessOut:
    """What is still missing before the application can be submitted."""
    violations = await service.completeness(access, application_id)
    return CompletenessOut(
        complete=not violations,
        violations=[ViolationOut.model_validate(v.as_dict()) for v in violations],
    )


@router.post(
    "/{application_id}/documents",
    response_model=DocumentUploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_upload(
    application_id: UUID, data: DocumentUploadIn, access: CanUpdate, service: Service
) -> DocumentUploadOut:
    """Announce a file and get a presigned URL: the browser PUTs it straight
    to the storage, then calls /confirm."""
    result = await service.request_upload(
        access, application_id, data.type, data.filename, data.content_type, data.size_bytes
    )
    return DocumentUploadOut(
        document=presenters.document(result.document), upload=presenters.upload(result.upload)
    )


@router.post("/{application_id}/documents/{document_id}/confirm", response_model=DocumentOut)
async def confirm_upload(
    application_id: UUID, document_id: UUID, access: CanUpdate, service: Service
) -> DocumentOut:
    return presenters.document(await service.confirm_upload(access, application_id, document_id))


@router.get("/{application_id}/documents/{document_id}/download", response_model=DownloadOut)
async def download_document(
    application_id: UUID, document_id: UUID, access: CanRead, service: Service
) -> DownloadOut:
    return DownloadOut(url=await service.download_url(access, application_id, document_id))


@router.delete("/{application_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    application_id: UUID, document_id: UUID, access: CanUpdate, service: Service
) -> None:
    await service.delete_document(access, application_id, document_id)


@router.post("/{application_id}/submit", response_model=ApplicationOut)
async def submit(application_id: UUID, access: CanUpdate, service: Service) -> ApplicationOut:
    return presenters.application(await service.submit(access, application_id))


@router.post(
    "/{application_id}/info-requests/{info_request_id}/answer", response_model=ApplicationOut
)
async def answer_info_request(
    application_id: UUID, info_request_id: UUID, access: CanUpdate, service: Service
) -> ApplicationOut:
    view = await service.answer_info_request(access, application_id, info_request_id)
    return presenters.application(view)


@router.post("/{application_id}/offer/accept", response_model=ApplicationOut)
async def accept_offer(application_id: UUID, access: CanUpdate, service: Service) -> ApplicationOut:
    return presenters.application(await service.accept_offer(access, application_id))


@router.post("/{application_id}/offer/decline", response_model=ApplicationOut)
async def decline_offer(
    application_id: UUID, access: CanUpdate, service: Service, data: ReasonIn | None = None
) -> ApplicationOut:
    reason = data.reason if data else None
    return presenters.application(await service.decline_offer(access, application_id, reason))


@router.post("/{application_id}/sign", response_model=SignOut)
async def sign(
    application_id: UUID, data: SignIn, request: Request, access: CanUpdate, service: Service
) -> SignOut:
    """Simulated signature: the password is asked once more (step-up), the
    document goes through the EDO mock; the response says `simulated: true`."""
    result = await service.sign(
        access,
        application_id,
        data.password.get_secret_value(),
        client_ip(request),
        request.headers.get("user-agent"),
    )
    return SignOut(
        application=presenters.application(result.view),
        signature=SignatureOut(
            signed_at=result.signature.signed_at,
            offer_hash=result.signature.offer_hash,
            edo_document_id=result.edo_document_id,
            simulated=result.simulated,
        ),
    )


@router.post("/{application_id}/cancel", response_model=ApplicationOut)
async def cancel(
    application_id: UUID, access: CanUpdate, service: Service, data: ReasonIn | None = None
) -> ApplicationOut:
    reason = data.reason if data else None
    return presenters.application(await service.cancel(access, application_id, reason))
