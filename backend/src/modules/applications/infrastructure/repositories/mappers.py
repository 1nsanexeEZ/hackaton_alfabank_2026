"""Aggregate <-> rows. Value objects are stored as JSON with Decimal amounts
as strings and datetimes in ISO format, so nothing loses precision."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from src.core.domain import Money
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.entities import Document, InfoRequest
from src.modules.applications.domain.enums import (
    ApplicationStatus,
    DocumentStatus,
    InfoRequestStatus,
)
from src.modules.applications.domain.fields_schema import ProductFieldsSchema
from src.modules.applications.domain.value_objects import (
    Actor,
    ApplicationNumber,
    BeneficiaryDeclaration,
    CollateralDeclaration,
    Consents,
    DecidedBy,
    DecisionSummary,
    Disbursement,
    DocumentRequirement,
    LoanRequest,
    Offer,
    OrganizationSnapshot,
    ProductTerms,
    ProfileConsent,
    Signature,
    StatusChange,
    ThirdParty,
)
from src.modules.applications.infrastructure.database.models import (
    ApplicationRecord,
    DocumentRecord,
    InfoRequestRecord,
    SignatureRecord,
    StatusHistoryRecord,
)

# --- primitives ---------------------------------------------------------------


def money_out(value: Money | None) -> dict[str, str] | None:
    return None if value is None else {"amount": str(value.amount), "currency": value.currency}


def money_in(value: dict[str, str] | None) -> Money | None:
    return None if value is None else Money(Decimal(value["amount"]), value["currency"])


def _money(value: dict[str, str]) -> Money:
    money = money_in(value)
    assert money is not None
    return money


def dt_out(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def dt_in(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _dt(value: str) -> datetime:
    moment = dt_in(value)
    assert moment is not None
    return moment


def _uuid(value: str | None) -> UUID | None:
    return None if value is None else UUID(value)


def aware(value: datetime | None) -> datetime | None:
    """SQLite gives naive datetimes back; everything stored is UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _aware(value: datetime) -> datetime:
    moment = aware(value)
    assert moment is not None
    return moment


# --- value objects ------------------------------------------------------------


def terms_out(terms: ProductTerms) -> dict[str, Any]:
    return {
        "code": terms.code,
        "version": terms.version,
        "amount_min": money_out(terms.amount_min),
        "amount_max": money_out(terms.amount_max),
        "term_min_months": terms.term_min_months,
        "term_max_months": terms.term_max_months,
        "rate_base": str(terms.rate_base),
        "rate_max": str(terms.rate_max),
        "repayment_options": list(terms.repayment_options),
        "facility": terms.facility,
        "collateral_required": terms.collateral_required,
        "collateral_required_from": money_out(terms.collateral_required_from),
        "required_documents": [
            {
                "type": r.type,
                "title": r.title,
                "required_from_amount": money_out(r.required_from_amount),
                "legal_forms": sorted(r.legal_forms),
            }
            for r in terms.required_documents
        ],
        "fields_schema": dict(terms.fields_schema.raw),
        "workflow_code": terms.workflow_code,
        "auto_decision_limit": money_out(terms.auto_decision_limit),
    }


def terms_in(data: dict[str, Any]) -> ProductTerms:
    return ProductTerms(
        code=data["code"],
        version=data["version"],
        amount_min=_money(data["amount_min"]),
        amount_max=_money(data["amount_max"]),
        term_min_months=data["term_min_months"],
        term_max_months=data["term_max_months"],
        rate_base=Decimal(data["rate_base"]),
        rate_max=Decimal(data["rate_max"]),
        repayment_options=tuple(data["repayment_options"]),
        facility=data["facility"],
        collateral_required=data["collateral_required"],
        collateral_required_from=money_in(data["collateral_required_from"]),
        required_documents=tuple(
            DocumentRequirement(
                type=r["type"],
                title=r["title"],
                required_from_amount=money_in(r["required_from_amount"]),
                legal_forms=frozenset(r["legal_forms"]),
            )
            for r in data["required_documents"]
        ),
        fields_schema=ProductFieldsSchema(data["fields_schema"]),
        workflow_code=data["workflow_code"],
        auto_decision_limit=_money(data["auto_decision_limit"]),
    )


def request_out(request: LoanRequest) -> dict[str, Any]:
    return {
        "amount": money_out(request.amount),
        "term_months": request.term_months,
        "purpose": request.purpose,
        "purpose_comment": request.purpose_comment,
    }


def request_in(data: dict[str, Any]) -> LoanRequest:
    return LoanRequest(
        amount=money_in(data.get("amount")),
        term_months=data.get("term_months"),
        purpose=data.get("purpose"),
        purpose_comment=data.get("purpose_comment"),
    )


def collateral_out(collateral: CollateralDeclaration | None) -> dict[str, Any] | None:
    if collateral is None:
        return None
    return {
        "type": collateral.type,
        "description": collateral.description,
        "declared_value": money_out(collateral.declared_value),
        "owner": collateral.owner,
        "owner_party": third_party_out(collateral.owner_party),
    }


def collateral_in(data: dict[str, Any] | None) -> CollateralDeclaration | None:
    if data is None:
        return None
    return CollateralDeclaration(
        type=data["type"],
        description=data["description"],
        declared_value=_money(data["declared_value"]),
        owner=data["owner"],
        owner_party=third_party_in(data.get("owner_party")),
    )


def third_party_out(party: ThirdParty | None) -> dict[str, Any] | None:
    if party is None:
        return None
    return {"kind": party.kind, "name": party.name, "inn": party.inn}


def third_party_in(data: dict[str, Any] | None) -> ThirdParty | None:
    if data is None:
        return None
    return ThirdParty(kind=data["kind"], name=data["name"], inn=data.get("inn"))


def beneficiary_out(declaration: BeneficiaryDeclaration | None) -> dict[str, Any] | None:
    if declaration is None:
        return None
    return {
        "acts_for_third_party": declaration.acts_for_third_party,
        "declared_by": str(declaration.declared_by),
        "declared_at": dt_out(declaration.declared_at),
        "beneficiary": third_party_out(declaration.beneficiary),
        "basis": declaration.basis,
    }


def beneficiary_in(data: dict[str, Any] | None) -> BeneficiaryDeclaration | None:
    if data is None:
        return None
    declared_at = dt_in(data["declared_at"])
    assert declared_at is not None
    return BeneficiaryDeclaration(
        acts_for_third_party=data["acts_for_third_party"],
        declared_by=UUID(data["declared_by"]),
        declared_at=declared_at,
        beneficiary=third_party_in(data.get("beneficiary")),
        basis=data.get("basis"),
    )


def _profile_consent_out(consent: ProfileConsent | None) -> dict[str, Any] | None:
    if consent is None:
        return None
    return {
        "given_by": str(consent.given_by),
        "given_at": dt_out(consent.given_at),
        "text_version": consent.text_version,
    }


def _profile_consent_in(data: dict[str, Any] | None) -> ProfileConsent | None:
    """Rows written before #152 have no such key."""
    if not data:
        return None
    given_at = dt_in(data["given_at"])
    if given_at is None:
        raise ValueError("A profile consent has no moment")
    return ProfileConsent(
        given_by=UUID(data["given_by"]), given_at=given_at, text_version=data["text_version"]
    )


def consents_out(consents: Consents) -> dict[str, Any]:
    return {
        "personal_data_at": dt_out(consents.personal_data_at),
        "credit_bureau_at": dt_out(consents.credit_bureau_at),
        "given_by": str(consents.given_by) if consents.given_by else None,
        "automated_decision_at": dt_out(consents.automated_decision_at),
        "personal_data_profile": _profile_consent_out(consents.personal_data_profile),
        "credit_bureau_profile": _profile_consent_out(consents.credit_bureau_profile),
    }


def consents_in(data: dict[str, Any]) -> Consents:
    return Consents(
        personal_data_at=dt_in(data.get("personal_data_at")),
        credit_bureau_at=dt_in(data.get("credit_bureau_at")),
        given_by=_uuid(data.get("given_by")),
        automated_decision_at=dt_in(data.get("automated_decision_at")),
        personal_data_profile=_profile_consent_in(data.get("personal_data_profile")),
        credit_bureau_profile=_profile_consent_in(data.get("credit_bureau_profile")),
    )


def snapshot_out(snapshot: OrganizationSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "organization_id": str(snapshot.organization_id),
        "legal_form": snapshot.legal_form,
        "taken_at": dt_out(snapshot.taken_at),
        "data": dict(snapshot.data),
    }


def snapshot_in(data: dict[str, Any] | None) -> OrganizationSnapshot | None:
    if data is None:
        return None
    return OrganizationSnapshot(
        organization_id=UUID(data["organization_id"]),
        legal_form=data["legal_form"],
        taken_at=_dt(data["taken_at"]),
        data=data["data"],
    )


def offer_out(offer: Offer | None) -> dict[str, Any] | None:
    if offer is None:
        return None
    return {
        "kind": offer.kind,
        "amount": money_out(offer.amount),
        "term_months": offer.term_months,
        "rate": str(offer.rate),
        "monthly_payment": money_out(offer.monthly_payment),
        "schedule_type": offer.schedule_type,
        "conditions": list(offer.conditions),
        "expires_at": dt_out(offer.expires_at),
        "decision_id": str(offer.decision_id),
    }


def offer_in(data: dict[str, Any] | None) -> Offer | None:
    if data is None:
        return None
    return Offer(
        kind=data["kind"],
        amount=_money(data["amount"]),
        term_months=data["term_months"],
        rate=Decimal(data["rate"]),
        monthly_payment=_money(data["monthly_payment"]),
        schedule_type=data["schedule_type"],
        conditions=tuple(data["conditions"]),
        expires_at=_dt(data["expires_at"]),
        decision_id=UUID(data["decision_id"]),
    )


def summary_out(summary: DecisionSummary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "outcome": summary.outcome,
        "client_explanation": summary.client_explanation,
        "improvement_hints": list(summary.improvement_hints),
        "alternative_product_code": summary.alternative_product_code,
    }


def summary_in(data: dict[str, Any] | None, decided_by: str | None) -> DecisionSummary | None:
    """`decided_by` is a column of its own, see ApplicationRecord."""
    if data is None:
        return None
    return DecisionSummary(
        outcome=data["outcome"],
        client_explanation=data["client_explanation"],
        improvement_hints=tuple(data["improvement_hints"]),
        alternative_product_code=data.get("alternative_product_code"),
        decided_by=cast(DecidedBy | None, decided_by),
    )


def disbursement_out(disbursement: Disbursement | None) -> dict[str, Any] | None:
    if disbursement is None:
        return None
    return {
        "reference": disbursement.reference,
        "disbursed_at": dt_out(disbursement.disbursed_at),
        "simulated": disbursement.simulated,
    }


def disbursement_in(data: dict[str, Any] | None) -> Disbursement | None:
    if data is None:
        return None
    return Disbursement(data["reference"], _dt(data["disbursed_at"]), data["simulated"])


# --- aggregate ----------------------------------------------------------------


def to_domain(record: ApplicationRecord) -> CreditApplication:
    application = CreditApplication(
        id=record.id,
        number=ApplicationNumber(record.number),
        organization_id=record.organization_id,
        applicant_account_id=record.applicant_account_id,
        product_terms=terms_in(record.product_terms),
        status=ApplicationStatus(record.status),
        created_at=_aware(record.created_at),
        updated_at=_aware(record.updated_at),
        request=request_in(record.request),
        product_fields=record.product_fields,
        collateral=collateral_in(record.collateral),
        consents=consents_in(record.consents),
        beneficiary=beneficiary_in(record.beneficiary),
        org_snapshot=snapshot_in(record.org_snapshot),
        documents=[_document_in(d) for d in record.documents],
        info_requests=[_info_request_in(r) for r in record.info_requests],
        offer=offer_in(record.offer),
        decision_summary=summary_in(record.decision_summary, record.decided_by),
        signature=_signature_in(record.signature),
        disbursement=disbursement_in(record.disbursement),
        client_stage=record.client_stage,
        history=[_history_in(h) for h in record.history],
        version=record.version,
        submitted_at=aware(record.submitted_at),
        closed_at=aware(record.closed_at),
    )
    return application


def new_record(application: CreditApplication) -> ApplicationRecord:
    record = ApplicationRecord(
        id=application.id,
        number=str(application.number),
        organization_id=application.organization_id,
        applicant_account_id=application.applicant_account_id,
        product_code=application.product_code,
        product_terms=terms_out(application.product_terms),
        created_at=application.created_at,
        documents=[],
        info_requests=[],
        history=[],
    )
    apply(application, record)
    return record


def apply(application: CreditApplication, record: ApplicationRecord) -> None:
    """Copy the aggregate state onto loaded rows (product terms and the
    number never change after creation)."""
    record.status = application.status.value
    record.client_stage = application.client_stage
    record.request = request_out(application.request)
    record.product_fields = dict(application.product_fields)
    record.collateral = collateral_out(application.collateral)
    record.consents = consents_out(application.consents)
    record.beneficiary = beneficiary_out(application.beneficiary)
    record.org_snapshot = snapshot_out(application.org_snapshot)
    record.offer = offer_out(application.offer)
    record.decision_summary = summary_out(application.decision_summary)
    summary = application.decision_summary
    record.decided_by = summary.decided_by if summary else None
    record.disbursement = disbursement_out(application.disbursement)
    record.offer_expires_at = application.offer.expires_at if application.offer else None
    record.updated_at = application.updated_at
    record.submitted_at = application.submitted_at
    record.closed_at = application.closed_at
    _sync_documents(application, record)
    _sync_info_requests(application, record)
    for change in application.history[len(record.history) :]:
        record.history.append(
            StatusHistoryRecord(
                from_status=change.from_status,
                to_status=change.to_status,
                at=change.at,
                actor_type=change.actor.kind,
                actor_id=change.actor.account_id,
                reason=change.reason,
            )
        )
    if application.signature is not None and record.signature is None:
        record.signature = SignatureRecord(
            signed_by=application.signature.signed_by,
            signed_at=application.signature.signed_at,
            offer_hash=application.signature.offer_hash,
        )


def _sync_documents(application: CreditApplication, record: ApplicationRecord) -> None:
    rows = {row.id: row for row in record.documents}
    keep = {d.id for d in application.documents}
    for row in list(record.documents):
        if row.id not in keep:
            record.documents.remove(row)
    for document in application.documents:
        row = rows.get(document.id)
        if row is None:
            row = DocumentRecord(id=document.id, application_id=application.id)
            record.documents.append(row)
        row.type = document.type
        row.filename = document.filename
        row.content_type = document.content_type
        row.size_bytes = document.size_bytes
        row.s3_key = document.s3_key
        row.status = document.status.value
        row.uploaded_by = document.uploaded_by
        row.created_at = document.created_at
        row.uploaded_at = document.uploaded_at
        row.info_request_id = document.info_request_id
        row.review_comment = document.review_comment


def _sync_info_requests(application: CreditApplication, record: ApplicationRecord) -> None:
    rows = {row.id: row for row in record.info_requests}
    for request in application.info_requests:
        row = rows.get(request.id)
        if row is None:
            row = InfoRequestRecord(id=request.id, application_id=application.id)
            record.info_requests.append(row)
        row.requested_fields = list(request.requested_fields)
        row.requested_documents = list(request.requested_documents)
        row.comment = request.comment
        row.status = request.status.value
        row.created_at = request.created_at
        row.due_at = request.due_at
        row.answered_at = request.answered_at
        row.answered_by = request.answered_by


def _document_in(row: DocumentRecord) -> Document:
    return Document(
        id=row.id,
        type=row.type,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        s3_key=row.s3_key,
        status=DocumentStatus(row.status),
        uploaded_by=row.uploaded_by,
        created_at=_aware(row.created_at),
        uploaded_at=aware(row.uploaded_at),
        info_request_id=row.info_request_id,
        review_comment=row.review_comment,
    )


def _info_request_in(row: InfoRequestRecord) -> InfoRequest:
    return InfoRequest(
        id=row.id,
        requested_fields=tuple(row.requested_fields),
        requested_documents=tuple(row.requested_documents),
        comment=row.comment,
        created_at=_aware(row.created_at),
        due_at=aware(row.due_at),
        status=InfoRequestStatus(row.status),
        answered_at=aware(row.answered_at),
        answered_by=row.answered_by,
    )


def _history_in(row: StatusHistoryRecord) -> StatusChange:
    actor = Actor(row.actor_type, row.actor_id)  # type: ignore[arg-type]
    return StatusChange(row.from_status, row.to_status, _aware(row.at), actor, row.reason)


def _signature_in(row: SignatureRecord | None) -> Signature | None:
    if row is None:
        return None
    return Signature(row.signed_by, _aware(row.signed_at), row.offer_hash, row.edo_document_id)
