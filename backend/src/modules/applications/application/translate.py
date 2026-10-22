"""Facade DTOs (ours and the neighbours') <-> domain objects."""

from datetime import datetime
from decimal import Decimal

from src.core.domain import Money
from src.core.exceptions.exceptions import ConflictError
from src.core.messaging.contracts import applications as contracts
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.serialization import from_jsonable, to_jsonable
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.entities import Document
from src.modules.applications.domain.events import (
    ApplicationCancelled,
    ApplicationEvent,
    ApplicationInfoProvided,
    ApplicationSigned,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferDeclined,
    OfferExpired,
)
from src.modules.applications.domain.fields_schema import ProductFieldsSchema
from src.modules.applications.domain.value_objects import (
    DocumentRequirement,
    OrganizationSnapshot,
    ProductTerms,
)
from src.modules.applications.facade import (
    ApplicationCardDTO,
    ApplicationSummaryDTO,
    CollateralDTO,
    ConsentsDTO,
    DecisionSummaryDTO,
    DocumentDTO,
    InfoRequestDTO,
    LoanRequestDTO,
    OfferDTO,
    ScoringInputDTO,
    StatusChangeDTO,
)
from src.modules.clients.facade import OrganizationSnapshotDTO
from src.modules.products.facade import ProductTermsDTO, RequiredDocumentDTO


def _money(value: Decimal | None) -> Money | None:
    return None if value is None else Money.of(value)


def terms_from_dto(dto: ProductTermsDTO) -> ProductTerms:
    return ProductTerms(
        code=dto.code,
        version=dto.version,
        amount_min=Money.of(dto.amount_min),
        amount_max=Money.of(dto.amount_max),
        term_min_months=dto.term_min_months,
        term_max_months=dto.term_max_months,
        rate_base=dto.rate_base,
        rate_max=dto.rate_max,
        repayment_options=tuple(dto.repayment_options),
        facility=dto.facility,
        collateral_required=dto.collateral_required,
        collateral_required_from=_money(dto.collateral_required_from),
        required_documents=tuple(
            DocumentRequirement(
                type=r.type,
                title=r.title,
                required_from_amount=_money(r.required_from_amount),
                legal_forms=frozenset(r.legal_forms),
            )
            for r in dto.required_documents
        ),
        fields_schema=ProductFieldsSchema(dto.application_fields_schema),
        workflow_code=dto.workflow_code,
        auto_decision_limit=Money.of(dto.auto_decision_limit),
    )


def terms_to_dto(terms: ProductTerms) -> ProductTermsDTO:
    return ProductTermsDTO(
        code=terms.code,
        version=terms.version,
        amount_min=terms.amount_min.amount,
        amount_max=terms.amount_max.amount,
        term_min_months=terms.term_min_months,
        term_max_months=terms.term_max_months,
        rate_base=terms.rate_base,
        rate_max=terms.rate_max,
        repayment_options=terms.repayment_options,  # type: ignore[arg-type]
        facility=terms.facility,  # type: ignore[arg-type]
        collateral_required=terms.collateral_required,
        collateral_required_from=(
            terms.collateral_required_from.amount if terms.collateral_required_from else None
        ),
        required_documents=tuple(
            RequiredDocumentDTO(
                type=r.type,
                title=r.title,
                required_from_amount=r.required_from_amount.amount
                if r.required_from_amount
                else None,
                legal_forms=tuple(sorted(r.legal_forms)),
            )
            for r in terms.required_documents
        ),
        application_fields_schema=dict(terms.fields_schema.raw),
        workflow_code=terms.workflow_code,
        auto_decision_limit=terms.auto_decision_limit.amount,
    )


def snapshot_from_dto(dto: OrganizationSnapshotDTO, taken_at: datetime) -> OrganizationSnapshot:
    return OrganizationSnapshot(
        organization_id=dto.id,
        legal_form=dto.legal_form,
        taken_at=taken_at,
        data=to_jsonable(dto),
    )


def snapshot_to_dto(snapshot: OrganizationSnapshot) -> OrganizationSnapshotDTO:
    return from_jsonable(OrganizationSnapshotDTO, dict(snapshot.data))


def document_dto(document: Document) -> DocumentDTO:
    return DocumentDTO(
        id=document.id,
        type=document.type,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status.value,  # type: ignore[arg-type]
        uploaded_by=document.uploaded_by,
        uploaded_at=document.uploaded_at,
        info_request_id=document.info_request_id,
        review_comment=document.review_comment,
    )


def request_dto(application: CreditApplication) -> LoanRequestDTO | None:
    """Only a complete request crosses the module border; a half-filled
    draft is edited through the applications API itself."""
    request = application.request
    if request.amount is None or request.term_months is None or request.purpose is None:
        return None
    return LoanRequestDTO(
        amount=request.amount.amount,
        term_months=request.term_months,
        purpose=request.purpose,
        purpose_comment=request.purpose_comment,
    )


def card(application: CreditApplication) -> ApplicationCardDTO:
    collateral = application.collateral
    consents = application.consents
    offer = application.offer
    summary = application.decision_summary
    return ApplicationCardDTO(
        id=application.id,
        number=str(application.number),
        organization_id=application.organization_id,
        applicant_account_id=application.applicant_account_id,
        product_code=application.product_code,
        product_terms=terms_to_dto(application.product_terms),
        request=request_dto(application),
        product_fields=dict(application.product_fields),
        collateral=CollateralDTO(
            type=collateral.type,  # type: ignore[arg-type]
            description=collateral.description,
            declared_value=collateral.declared_value.amount,
            owner=collateral.owner,
        )
        if collateral
        else None,
        consents=ConsentsDTO(
            consents.personal_data_at, consents.credit_bureau_at, consents.given_by
        ),
        org_snapshot=snapshot_to_dto(application.org_snapshot)
        if application.org_snapshot
        else None,
        status=application.status.value,  # type: ignore[arg-type]
        client_stage=application.client_stage,
        documents=tuple(document_dto(d) for d in application.documents),
        info_requests=tuple(
            InfoRequestDTO(
                id=r.id,
                requested_fields=r.requested_fields,
                requested_documents=r.requested_documents,
                comment=r.comment,
                created_at=r.created_at,
                due_at=r.due_at,
                status=r.status.value,  # type: ignore[arg-type]
                answered_at=r.answered_at,
            )
            for r in application.info_requests
        ),
        offer=OfferDTO(
            kind=offer.kind,
            amount=offer.amount.amount,
            term_months=offer.term_months,
            rate=offer.rate,
            monthly_payment=offer.monthly_payment.amount,
            schedule_type=offer.schedule_type,
            conditions=offer.conditions,
            expires_at=offer.expires_at,
            decision_id=offer.decision_id,
        )
        if offer
        else None,
        decision_summary=DecisionSummaryDTO(
            outcome=summary.outcome,
            client_explanation=summary.client_explanation,
            improvement_hints=summary.improvement_hints,
            alternative_product_code=summary.alternative_product_code,
        )
        if summary
        else None,
        history=tuple(
            StatusChangeDTO(h.from_status, h.to_status, h.at, h.actor.kind, h.reason)
            for h in application.history
        ),
        version=application.version,
        created_at=application.created_at,
        updated_at=application.updated_at,
        submitted_at=application.submitted_at,
        closed_at=application.closed_at,
        disbursement_reference=application.disbursement.reference
        if application.disbursement
        else None,
    )


def summary_dto(application: CreditApplication) -> ApplicationSummaryDTO:
    request = application.request
    return ApplicationSummaryDTO(
        id=application.id,
        number=str(application.number),
        organization_id=application.organization_id,
        product_code=application.product_code,
        amount=request.amount.amount if request.amount else None,
        term_months=request.term_months,
        status=application.status.value,  # type: ignore[arg-type]
        client_stage=application.client_stage,
        updated_at=application.updated_at,
        submitted_at=application.submitted_at,
    )


def scoring_input(application: CreditApplication) -> ScoringInputDTO:
    """Data frozen at submission; a draft has nothing to score yet."""
    snapshot = application.org_snapshot
    request = request_dto(application)
    if snapshot is None or request is None or application.submitted_at is None:
        raise ConflictError("Application is not submitted yet", details={"code": "not_submitted"})
    collateral = card(application).collateral
    return ScoringInputDTO(
        application_id=application.id,
        organization_id=application.organization_id,
        product_code=application.product_code,
        request=request,
        organization=snapshot_to_dto(snapshot),
        product_terms=terms_to_dto(application.product_terms),
        collateral=collateral,
        statement_document_ids=tuple(
            d.id for d in application.uploaded_documents("bank_statement")
        ),
        credit_bureau_consent_at=application.consents.credit_bureau_at,
        submitted_at=application.submitted_at,
    )


def to_contract(event: ApplicationEvent) -> IntegrationMessage:
    ids = {"application_id": event.application_id, "organization_id": event.organization_id}
    match event:
        case ApplicationSubmitted():
            return contracts.ApplicationSubmitted(
                **ids,
                product_code=event.product_code,
                amount=event.amount.amount,
                term_months=event.term_months,
                purpose=event.purpose,
            )
        case ApplicationStatusChanged():
            return contracts.ApplicationStatusChanged(
                **ids,
                from_status=event.from_status,
                to_status=event.to_status,
                client_stage=event.client_stage,
            )
        case ApplicationInfoProvided():
            return contracts.ApplicationInfoProvided(
                **ids, info_request_id=event.info_request_id, document_ids=list(event.document_ids)
            )
        case OfferAccepted():
            return contracts.OfferAccepted(**ids)
        case OfferDeclined():
            return contracts.OfferDeclined(**ids)
        case OfferExpired():
            return contracts.OfferExpired(**ids)
        case ApplicationSigned():
            return contracts.ApplicationSigned(**ids, signed_by=event.signed_by)
        case ApplicationCancelled():
            return contracts.ApplicationCancelled(**ids)
    raise TypeError(f"No integration contract for {type(event).__name__}")
