from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from src.modules.applications.domain.contract_documents import ContractDocumentKind
from src.modules.applications.domain.value_objects import DecidedBy
from src.modules.applications.presentation.dependencies import (
    AcceptOfferDep,
    AnswerInfoRequestDep,
    CancelDep,
    CanCreate,
    CanRead,
    CanUpdate,
    CheckCompletenessDep,
    ConfirmUploadDep,
    ContractViewDep,
    CreateDraftDep,
    DeclineOfferDep,
    DeleteDocumentDep,
    DownloadContractDep,
    DownloadUrlDep,
    GetApplicationDep,
    ListApplicationsDep,
    RequestUploadDep,
    SealContractDep,
    SignDep,
    SubmitDep,
    UpdateDraftDep,
    client_ip,
)
from src.modules.applications.presentation.schemas.applications import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationOut,
    ApplicationUpdate,
    CompletenessOut,
    ReasonIn,
    ViolationOut,
)
from src.modules.applications.presentation.schemas.contracts import ContractOut, SignIn, SignOut
from src.modules.applications.presentation.schemas.documents import (
    DocumentOut,
    DocumentUploadIn,
    DocumentUploadOut,
    DownloadOut,
)

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_draft(
    data: ApplicationCreate, access: CanCreate, use_case: CreateDraftDep
) -> ApplicationOut:
    """Draft for a company and a product; requisites come from the bank's data."""
    view = await use_case.execute(access, data.organization_id, data.product_code)
    return ApplicationOut.model_validate(view)


@router.get("", response_model=list[ApplicationListItem])
async def list_applications(
    access: CanRead,
    use_case: ListApplicationsDep,
    organization_id: UUID | None = None,
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    decided_by: DecidedBy | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ApplicationListItem]:
    """Newest first. `decided_by=auto` — the decisions the client got from the automatic
    policy without a person; combines with `status`."""
    applications = await use_case.execute(
        access, organization_id, status_filter, limit, offset, decided_by
    )
    return [ApplicationListItem.model_validate(application) for application in applications]


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: UUID, access: CanRead, use_case: GetApplicationDep
) -> ApplicationOut:
    return ApplicationOut.model_validate(await use_case.execute(access, application_id))


@router.patch("/{application_id}", response_model=ApplicationOut)
async def update_draft(
    application_id: UUID, data: ApplicationUpdate, access: CanUpdate, use_case: UpdateDraftDep
) -> ApplicationOut:
    view = await use_case.execute(access, application_id, data.to_dto())
    return ApplicationOut.model_validate(view)


@router.get("/{application_id}/completeness", response_model=CompletenessOut)
async def completeness(
    application_id: UUID, access: CanRead, use_case: CheckCompletenessDep
) -> CompletenessOut:
    """What is still missing before the application can be submitted."""
    report = await use_case.execute(access, application_id)
    return CompletenessOut(
        complete=report.complete,
        violations=[ViolationOut.model_validate(v) for v in report.violations],
    )


@router.post(
    "/{application_id}/documents",
    response_model=DocumentUploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_upload(
    application_id: UUID, data: DocumentUploadIn, access: CanUpdate, use_case: RequestUploadDep
) -> DocumentUploadOut:
    """Announce a file and get a presigned URL: the browser PUTs it straight
    to the storage, then calls /confirm."""
    result = await use_case.execute(
        access, application_id, data.type, data.filename, data.content_type, data.size_bytes
    )
    return DocumentUploadOut.model_validate(result)


@router.post("/{application_id}/documents/{document_id}/confirm", response_model=DocumentOut)
async def confirm_upload(
    application_id: UUID, document_id: UUID, access: CanUpdate, use_case: ConfirmUploadDep
) -> DocumentOut:
    return DocumentOut.model_validate(await use_case.execute(access, application_id, document_id))


@router.get("/{application_id}/documents/{document_id}/download", response_model=DownloadOut)
async def download_document(
    application_id: UUID, document_id: UUID, access: CanRead, use_case: DownloadUrlDep
) -> DownloadOut:
    return DownloadOut(url=await use_case.execute(access, application_id, document_id))


@router.delete("/{application_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    application_id: UUID, document_id: UUID, access: CanUpdate, use_case: DeleteDocumentDep
) -> None:
    await use_case.execute(access, application_id, document_id)


@router.post("/{application_id}/submit", response_model=ApplicationOut)
async def submit(application_id: UUID, access: CanUpdate, use_case: SubmitDep) -> ApplicationOut:
    return ApplicationOut.model_validate(await use_case.execute(access, application_id))


@router.post(
    "/{application_id}/info-requests/{info_request_id}/answer", response_model=ApplicationOut
)
async def answer_info_request(
    application_id: UUID, info_request_id: UUID, access: CanUpdate, use_case: AnswerInfoRequestDep
) -> ApplicationOut:
    view = await use_case.execute(access, application_id, info_request_id)
    return ApplicationOut.model_validate(view)


@router.post("/{application_id}/offer/accept", response_model=ApplicationOut)
async def accept_offer(
    application_id: UUID, access: CanUpdate, use_case: AcceptOfferDep
) -> ApplicationOut:
    return ApplicationOut.model_validate(await use_case.execute(access, application_id))


@router.post("/{application_id}/offer/decline", response_model=ApplicationOut)
async def decline_offer(
    application_id: UUID, access: CanUpdate, use_case: DeclineOfferDep, data: ReasonIn | None = None
) -> ApplicationOut:
    reason = data.reason if data else None
    return ApplicationOut.model_validate(await use_case.execute(access, application_id, reason))


@router.get("/{application_id}/contract", response_model=ContractOut)
async def contract(application_id: UUID, access: CanRead, use_case: ContractViewDep) -> ContractOut:
    """The loan contract to show before signing: borrower, terms, schedule
    and who may sign. From `signing` on; before that 409 `contract_not_ready`.
    `document` is its PDF: the draft until the client signs, then the copy
    sealed by the bank; `uid` — the deal identifier of the credit history."""
    return ContractOut.model_validate(await use_case.execute(access, application_id))


@router.get(
    "/{application_id}/contract/document",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The PDF itself"}},
)
async def contract_document(
    application_id: UUID,
    access: CanRead,
    use_case: DownloadContractDep,
    kind: Annotated[Literal["draft", "signed"] | None, Query()] = None,
) -> Response:
    """The contract PDF: `kind` = draft or signed, by default the latest one.
    409 `contract_not_ready` before the offer is accepted, `document_pending`
    while it is being made."""
    document = await use_case.execute(
        access, application_id, ContractDocumentKind(kind) if kind else None
    )
    return Response(
        content=document.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename)}",
            "X-Content-SHA256": document.sha256,
        },
    )


@router.post("/{application_id}/sign", response_model=SignOut)
async def sign(
    application_id: UUID,
    data: SignIn,
    request: Request,
    access: CanUpdate,
    use_case: SignDep,
    seal: SealContractDep,
) -> SignOut:
    """The client's simple electronic signature: the password once more
    (step-up), `offer_hash` and `document_hash` of the draft it read, the
    version of the rules it accepted. A changed offer — 409 `offer_changed`, a
    changed draft — 422 `document_changed`, old rules — 422 `rules_outdated`.
    Right after it the bank seals the contract PDF with its signature."""
    result = await use_case.execute(
        access,
        application_id,
        data.password.get_secret_value(),
        data.offer_hash,
        client_ip(request),
        request.headers.get("user-agent"),
        data.document_hash,
        data.rules_version,
    )
    await seal.execute(application_id)
    return SignOut.model_validate(result)


@router.post("/{application_id}/cancel", response_model=ApplicationOut)
async def cancel(
    application_id: UUID, access: CanUpdate, use_case: CancelDep, data: ReasonIn | None = None
) -> ApplicationOut:
    reason = data.reason if data else None
    return ApplicationOut.model_validate(await use_case.execute(access, application_id, reason))
