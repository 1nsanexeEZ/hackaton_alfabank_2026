"""Domain -> response schemas."""

from typing import Any

from src.applications.api import schemas
from src.applications.application.ports import PresignedUpload
from src.applications.application.service import ApplicationView
from src.applications.application.translate import terms_to_dto
from src.applications.domain.application import CreditApplication
from src.applications.domain.entities import Document
from src.applications.domain.statuses import ApplicationStatus
from src.clients.facade import OrgPermission
from src.core.serialization import to_jsonable

S = ApplicationStatus
SUBMIT = OrgPermission.SUBMIT_APPLICATION.value
SIGN = OrgPermission.SIGN.value

# status -> (action, right inside the company it needs)
_ACTIONS: dict[ApplicationStatus, list[tuple[str, str]]] = {
    S.DRAFT: [
        ("edit", SUBMIT),
        ("upload_document", SUBMIT),
        ("submit", SUBMIT),
        ("cancel", SUBMIT),
    ],
    S.SUBMITTED: [("cancel", SUBMIT)],
    S.INFO_REQUESTED: [
        ("upload_document", SUBMIT),
        ("answer_info_request", SUBMIT),
        ("cancel", SUBMIT),
    ],
    S.OFFER_READY: [("accept_offer", SUBMIT), ("decline_offer", SUBMIT), ("cancel", SUBMIT)],
    S.SIGNING: [("sign", SIGN)],
}


def available_actions(status: ApplicationStatus, permissions: frozenset[str]) -> list[str]:
    return [action for action, needs in _ACTIONS.get(status, []) if needs in permissions]


def document(document: Document) -> schemas.DocumentOut:
    return schemas.DocumentOut(
        id=document.id,
        type=document.type,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status.value,
        uploaded_at=document.uploaded_at,
        info_request_id=document.info_request_id,
    )


def upload(upload: PresignedUpload) -> schemas.PresignedUploadOut:
    return schemas.PresignedUploadOut(
        url=upload.url, method=upload.method, headers=upload.headers, expires_at=upload.expires_at
    )


def application(view: ApplicationView) -> schemas.ApplicationOut:
    app = view.application
    request = app.request
    organization_data: dict[str, Any] | None = None
    if app.org_snapshot is not None:
        organization_data = dict(app.org_snapshot.data)
    elif view.organization is not None:
        organization_data = to_jsonable(view.organization)
    return schemas.ApplicationOut(
        id=app.id,
        number=str(app.number),
        organization_id=app.organization_id,
        product_code=app.product_code,
        status=app.status.value,
        client_stage=app.client_stage,
        version=app.version,
        request=schemas.LoanRequestOut(
            amount=request.amount.amount if request.amount else None,
            term_months=request.term_months,
            purpose=request.purpose,
            purpose_comment=request.purpose_comment,
        ),
        product_fields=dict(app.product_fields),
        collateral=schemas.CollateralOut(
            type=app.collateral.type,
            description=app.collateral.description,
            declared_value=app.collateral.declared_value.amount,
            owner=app.collateral.owner,
        )
        if app.collateral
        else None,
        consents=schemas.ConsentsOut(
            personal_data_at=app.consents.personal_data_at,
            credit_bureau_at=app.consents.credit_bureau_at,
        ),
        product_terms=schemas.ProductTermsOut.model_validate(
            to_jsonable(terms_to_dto(app.product_terms))
        ),
        organization=schemas.OrganizationOut.model_validate(organization_data)
        if organization_data
        else None,
        documents=[document(d) for d in app.documents],
        info_requests=[
            schemas.InfoRequestOut(
                id=r.id,
                requested_fields=list(r.requested_fields),
                requested_documents=list(r.requested_documents),
                comment=r.comment,
                status=r.status.value,
                created_at=r.created_at,
                due_at=r.due_at,
                answered_at=r.answered_at,
            )
            for r in app.info_requests
        ],
        offer=schemas.OfferOut(
            kind=app.offer.kind,
            amount=app.offer.amount.amount,
            term_months=app.offer.term_months,
            rate=app.offer.rate,
            monthly_payment=app.offer.monthly_payment.amount,
            schedule_type=app.offer.schedule_type,
            conditions=list(app.offer.conditions),
            expires_at=app.offer.expires_at,
        )
        if app.offer
        else None,
        decision_summary=schemas.DecisionSummaryOut(
            outcome=app.decision_summary.outcome,
            client_explanation=app.decision_summary.client_explanation,
            improvement_hints=list(app.decision_summary.improvement_hints),
            alternative_product_code=app.decision_summary.alternative_product_code,
        )
        if app.decision_summary
        else None,
        disbursement=schemas.DisbursementOut(
            reference=app.disbursement.reference,
            disbursed_at=app.disbursement.disbursed_at,
            simulated=app.disbursement.simulated,
        )
        if app.disbursement
        else None,
        history=[
            schemas.StatusChangeOut(
                from_status=h.from_status,
                to_status=h.to_status,
                at=h.at,
                actor=h.actor.kind,
                reason=h.reason,
            )
            for h in app.history
        ],
        available_actions=available_actions(app.status, view.my_permissions),
        my_permissions=sorted(view.my_permissions),
        created_at=app.created_at,
        updated_at=app.updated_at,
        submitted_at=app.submitted_at,
        closed_at=app.closed_at,
    )


def list_item(app: CreditApplication) -> schemas.ApplicationListItem:
    return schemas.ApplicationListItem(
        id=app.id,
        number=str(app.number),
        organization_id=app.organization_id,
        product_code=app.product_code,
        status=app.status.value,
        client_stage=app.client_stage,
        amount=app.request.amount.amount if app.request.amount else None,
        term_months=app.request.term_months,
        updated_at=app.updated_at,
        submitted_at=app.submitted_at,
    )
