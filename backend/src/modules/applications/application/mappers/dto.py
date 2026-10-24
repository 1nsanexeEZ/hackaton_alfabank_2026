"""DTOs (ours and the neighbours') <-> domain objects."""

from datetime import datetime
from decimal import Decimal

from src.core.domain import Money
from src.core.exceptions.exceptions import ConflictError
from src.core.serialization import from_jsonable, to_jsonable
from src.modules.applications.application.dto.applications import (
    ApplicationCardDTO,
    ApplicationSummaryDTO,
    BeneficiaryDTO,
    CollateralDTO,
    ConsentsDTO,
    ConsentSource,
    DecisionSummaryDTO,
    DocumentDTO,
    InfoRequestDTO,
    LoanRequestDTO,
    OfferDTO,
    ScoringInputDTO,
    StatusChangeDTO,
    ThirdPartyDTO,
)
from src.modules.applications.application.dto.drafts import DraftRequestDTO
from src.modules.applications.application.dto.views import (
    ApplicationViewDTO,
    ContractDTO,
    ContractSignatureDTO,
    ContractSignerDTO,
    DisbursementDTO,
)
from src.modules.applications.domain.actions import available_actions
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.entities import Document, InfoRequest
from src.modules.applications.domain.fields_schema import ProductFieldsSchema
from src.modules.applications.domain.value_objects import (
    BeneficiaryDeclaration,
    CollateralDeclaration,
    Consents,
    DecisionSummary,
    DocumentRequirement,
    LoanRequest,
    Offer,
    OrganizationSnapshot,
    ProductTerms,
    ProfileConsent,
    ThirdParty,
)
from src.modules.clients.facade import OrganizationSnapshotDTO
from src.modules.identity.facade import ConsentDTO
from src.modules.products.facade import PaymentScheduleDTO, ProductTermsDTO, RequiredDocumentDTO


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


def loan_request(dto: DraftRequestDTO) -> LoanRequest:
    return LoanRequest(
        amount=Money.of(dto.amount) if dto.amount is not None else None,
        term_months=dto.term_months,
        purpose=dto.purpose,
        purpose_comment=dto.purpose_comment,
    )


def collateral_declaration(dto: CollateralDTO) -> CollateralDeclaration:
    return CollateralDeclaration(
        type=dto.type,
        description=dto.description,
        declared_value=Money.of(dto.declared_value),
        owner=dto.owner,
        owner_party=third_party(dto.owner_party),
    )


def third_party(dto: ThirdPartyDTO | None) -> ThirdParty | None:
    if dto is None:
        return None
    return ThirdParty(kind=dto.kind, name=dto.name, inn=dto.inn)


def third_party_dto(party: ThirdParty | None) -> ThirdPartyDTO | None:
    if party is None:
        return None
    return ThirdPartyDTO(kind=party.kind, name=party.name, inn=party.inn)


def beneficiary_dto(declaration: BeneficiaryDeclaration | None) -> BeneficiaryDTO | None:
    if declaration is None:
        return None
    return BeneficiaryDTO(
        acts_for_third_party=declaration.acts_for_third_party,
        declared_by=declaration.declared_by,
        declared_at=declaration.declared_at,
        beneficiary=third_party_dto(declaration.beneficiary),
        basis=declaration.basis,
    )


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


def collateral_dto(collateral: CollateralDeclaration | None) -> CollateralDTO | None:
    if collateral is None:
        return None
    return CollateralDTO(
        type=collateral.type,  # type: ignore[arg-type]
        description=collateral.description,
        declared_value=collateral.declared_value.amount,
        owner=collateral.owner,
        owner_party=third_party_dto(collateral.owner_party),
    )


def profile_consent(consent: ConsentDTO | None) -> ProfileConsent | None:
    if consent is None:
        return None
    return ProfileConsent(consent.account_id, consent.given_at, consent.text_version)


def _consent_source(at: datetime | None, profile: ProfileConsent | None) -> ConsentSource | None:
    if at is None:
        return None
    return "application" if profile is None else "profile"


def consents_dto(consents: Consents) -> ConsentsDTO:
    return ConsentsDTO(
        consents.personal_data_at,
        consents.credit_bureau_at,
        consents.given_by,
        consents.automated_decision_at,
        personal_data_source=_consent_source(
            consents.personal_data_at, consents.personal_data_profile
        ),
        credit_bureau_source=_consent_source(
            consents.credit_bureau_at, consents.credit_bureau_profile
        ),
    )


def info_request_dto(request: InfoRequest) -> InfoRequestDTO:
    return InfoRequestDTO(
        id=request.id,
        requested_fields=request.requested_fields,
        requested_documents=request.requested_documents,
        comment=request.comment,
        created_at=request.created_at,
        due_at=request.due_at,
        status=request.status.value,  # type: ignore[arg-type]
        answered_at=request.answered_at,
    )


def offer_dto(offer: Offer) -> OfferDTO:
    return OfferDTO(
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


def decision_dto(summary: DecisionSummary) -> DecisionSummaryDTO:
    return DecisionSummaryDTO(
        outcome=summary.outcome,
        client_explanation=summary.client_explanation,
        improvement_hints=summary.improvement_hints,
        alternative_product_code=summary.alternative_product_code,
    )


def history_dto(application: CreditApplication) -> tuple[StatusChangeDTO, ...]:
    return tuple(
        StatusChangeDTO(h.from_status, h.to_status, h.at, h.actor.kind, h.reason)
        for h in application.history
    )


def card(application: CreditApplication) -> ApplicationCardDTO:
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
        collateral=collateral_dto(application.collateral),
        consents=consents_dto(application.consents),
        org_snapshot=snapshot_to_dto(application.org_snapshot)
        if application.org_snapshot
        else None,
        status=application.status.value,  # type: ignore[arg-type]
        client_stage=application.client_stage,
        documents=tuple(document_dto(d) for d in application.documents),
        info_requests=tuple(info_request_dto(r) for r in application.info_requests),
        offer=offer_dto(offer) if offer else None,
        decision_summary=decision_dto(summary) if summary else None,
        history=history_dto(application),
        version=application.version,
        created_at=application.created_at,
        updated_at=application.updated_at,
        submitted_at=application.submitted_at,
        closed_at=application.closed_at,
        disbursement_reference=application.disbursement.reference
        if application.disbursement
        else None,
        beneficiary=beneficiary_dto(application.beneficiary),
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
    return ScoringInputDTO(
        application_id=application.id,
        organization_id=application.organization_id,
        product_code=application.product_code,
        request=request,
        organization=snapshot_to_dto(snapshot),
        product_terms=terms_to_dto(application.product_terms),
        collateral=collateral_dto(application.collateral),
        statement_document_ids=tuple(
            d.id for d in application.uploaded_documents("bank_statement")
        ),
        credit_bureau_consent_at=application.consents.credit_bureau_at,
        submitted_at=application.submitted_at,
        applicant_account_id=application.applicant_account_id,
        automated_decision_consent_at=application.consents.automated_decision_at,
        beneficiary=beneficiary_dto(application.beneficiary),
    )


def application_view(
    application: CreditApplication,
    organization: OrganizationSnapshotDTO | None,
    permissions: frozenset[str],
) -> ApplicationViewDTO:
    """The application for its client. `organization` — live company data for
    a draft (prefilled requisites); after submission the frozen snapshot inside
    the application is the source."""
    request = application.request
    organization_data = None
    if application.org_snapshot is not None:
        organization_data = dict(application.org_snapshot.data)
    elif organization is not None:
        organization_data = to_jsonable(organization)
    offer = application.offer
    summary = application.decision_summary
    disbursement = application.disbursement
    return ApplicationViewDTO(
        id=application.id,
        number=str(application.number),
        organization_id=application.organization_id,
        product_code=application.product_code,
        status=application.status.value,
        client_stage=application.client_stage,
        version=application.version,
        request=DraftRequestDTO(
            amount=request.amount.amount if request.amount else None,
            term_months=request.term_months,
            purpose=request.purpose,
            purpose_comment=request.purpose_comment,
        ),
        product_fields=dict(application.product_fields),
        collateral=collateral_dto(application.collateral),
        consents=consents_dto(application.consents),
        product_terms=terms_to_dto(application.product_terms),
        organization=organization_data or None,
        documents=tuple(document_dto(d) for d in application.documents),
        info_requests=tuple(info_request_dto(r) for r in application.info_requests),
        offer=offer_dto(offer) if offer else None,
        decision_summary=decision_dto(summary) if summary else None,
        disbursement=DisbursementDTO(
            reference=disbursement.reference,
            disbursed_at=disbursement.disbursed_at,
            simulated=disbursement.simulated,
        )
        if disbursement
        else None,
        history=history_dto(application),
        available_actions=tuple(available_actions(application.status, permissions)),
        my_permissions=tuple(sorted(permissions)),
        created_at=application.created_at,
        updated_at=application.updated_at,
        submitted_at=application.submitted_at,
        closed_at=application.closed_at,
        beneficiary=beneficiary_dto(application.beneficiary),
    )


def contract_dto(
    application: CreditApplication,
    offer: Offer,
    borrower: OrganizationSnapshotDTO,
    signers: tuple[ContractSignerDTO, ...],
    schedule: PaymentScheduleDTO,
    simulated: bool,
) -> ContractDTO:
    signature = application.signature
    return ContractDTO(
        number=str(application.number),
        offer_hash=offer.fingerprint(),
        status="signed" if signature else "unsigned",
        borrower=borrower,
        signers=signers,
        terms=offer_dto(offer),
        schedule=schedule,
        signature=ContractSignatureDTO(
            signed_by=signature.signed_by,
            signed_at=signature.signed_at,
            edo_document_id=signature.edo_document_id,
            simulated=simulated,
        )
        if signature
        else None,
    )
