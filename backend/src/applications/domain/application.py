"""CreditApplication — the aggregate root of the module.

The only owner of the business status: every transition goes through a
method here, a forbidden one raises InvalidStatusTransitionError. Client
actions (edit, submit, answer, accept, sign, cancel) and process commands
(start review, request info, offer, reject, disbursed) meet in one place.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Self
from uuid import UUID

from src.applications.domain.entities import (
    OPTIONAL_DOCUMENT_TYPES,
    Document,
    DocumentStatus,
    InfoRequest,
    InfoRequestStatus,
)
from src.applications.domain.events import (
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
from src.applications.domain.statuses import (
    FINAL_STATUSES,
    ApplicationStatus,
    ensure_transition,
)
from src.applications.domain.value_objects import (
    PROCESS,
    SYSTEM,
    Actor,
    ApplicationNumber,
    CollateralDeclaration,
    Consents,
    DecisionSummary,
    LoanRequest,
    Offer,
    OrganizationSnapshot,
    ProductTerms,
    Signature,
    StatusChange,
    Violation,
)
from src.core.exceptions.exceptions import ConflictError, NotFoundError, ValidationError

S = ApplicationStatus


class CreditApplication:
    def __init__(
        self,
        *,
        id: UUID,
        number: ApplicationNumber,
        organization_id: UUID,
        applicant_account_id: UUID,
        product_terms: ProductTerms,
        status: ApplicationStatus,
        created_at: datetime,
        updated_at: datetime,
        request: LoanRequest | None = None,
        product_fields: Mapping[str, Any] | None = None,
        collateral: CollateralDeclaration | None = None,
        consents: Consents | None = None,
        org_snapshot: OrganizationSnapshot | None = None,
        documents: list[Document] | None = None,
        info_requests: list[InfoRequest] | None = None,
        offer: Offer | None = None,
        decision_summary: DecisionSummary | None = None,
        signature: Signature | None = None,
        client_stage: str | None = None,
        history: list[StatusChange] | None = None,
        version: int = 1,
        submitted_at: datetime | None = None,
        closed_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.number = number
        self.organization_id = organization_id
        self.applicant_account_id = applicant_account_id
        self.product_terms = product_terms
        self.status = status
        self.request = request or LoanRequest()
        self.product_fields: dict[str, Any] = dict(product_fields or {})
        self.collateral = collateral
        self.consents = consents or Consents()
        self.org_snapshot = org_snapshot
        self.documents: list[Document] = list(documents or [])
        self.info_requests: list[InfoRequest] = list(info_requests or [])
        self.offer = offer
        self.decision_summary = decision_summary
        self.signature = signature
        self.client_stage = client_stage
        self.history: list[StatusChange] = list(history or [])
        self.version = version
        self.created_at = created_at
        self.updated_at = updated_at
        self.submitted_at = submitted_at
        self.closed_at = closed_at
        self._events: list[ApplicationEvent] = []

    @classmethod
    def create_draft(
        cls,
        *,
        id: UUID,
        number: ApplicationNumber,
        organization_id: UUID,
        applicant_account_id: UUID,
        product_terms: ProductTerms,
        now: datetime,
    ) -> Self:
        application = cls(
            id=id,
            number=number,
            organization_id=organization_id,
            applicant_account_id=applicant_account_id,
            product_terms=product_terms,
            status=S.DRAFT,
            created_at=now,
            updated_at=now,
        )
        application.history.append(
            StatusChange(None, S.DRAFT.value, now, Actor.client(applicant_account_id))
        )
        return application

    # --- reading ------------------------------------------------------------

    @property
    def product_code(self) -> str:
        return self.product_terms.code

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES

    @property
    def open_info_request(self) -> InfoRequest | None:
        return next((r for r in self.info_requests if r.is_open), None)

    def document(self, document_id: UUID) -> Document:
        for document in self.documents:
            if document.id == document_id:
                return document
        raise NotFoundError("Document not found")

    def info_request(self, info_request_id: UUID) -> InfoRequest:
        for info_request in self.info_requests:
            if info_request.id == info_request_id:
                return info_request
        raise NotFoundError("Information request not found")

    def uploaded_documents(self, document_type: str | None = None) -> list[Document]:
        return [
            d
            for d in self.documents
            if d.is_uploaded and (document_type is None or d.type == document_type)
        ]

    def pull_events(self) -> list[ApplicationEvent]:
        events, self._events = self._events, []
        return events

    def check_version(self, expected: int) -> None:
        """Optimistic locking for draft autosave: a stale form gets 409."""
        if expected != self.version:
            raise ConflictError(
                "Application was changed by someone else, reload it",
                details={"code": "version_conflict", "version": self.version},
            )

    # --- editing ------------------------------------------------------------

    def change_request(self, request: LoanRequest, now: datetime) -> None:
        self._ensure_editable("request")
        self.request = request
        self.updated_at = now

    def change_product_fields(self, values: Mapping[str, Any], now: datetime) -> None:
        """Merge: a key with None removes the value."""
        merged = {**self.product_fields, **values}
        merged = {key: value for key, value in merged.items() if value is not None}
        if self.status is S.INFO_REQUESTED:
            request = self.open_info_request
            changed = [k for k in values if self.product_fields.get(k) != values[k]]
            allowed = request is not None and (
                request.allows_field("product_fields")
                or all(request.allows_field(k) for k in changed)
            )
            if not allowed:
                raise self._not_editable("product_fields")
        else:
            self._ensure_editable("product_fields")
        errors = self.product_terms.fields_schema.validate(merged, partial=True)
        if errors:
            raise ValidationError(
                "Product fields are invalid",
                details={
                    "violations": [
                        Violation(e.code, f"product_fields.{e.path}").as_dict() for e in errors
                    ]
                },
            )
        self.product_fields = merged
        self.updated_at = now

    def change_collateral(self, collateral: CollateralDeclaration | None, now: datetime) -> None:
        self._ensure_editable("collateral")
        self.collateral = collateral
        self.updated_at = now

    def set_consents(
        self, *, personal_data: bool, credit_bureau: bool, account_id: UUID, now: datetime
    ) -> None:
        """A consent already given keeps its original moment."""
        self._ensure_editable("consents")
        current = self.consents
        self.consents = Consents(
            personal_data_at=(current.personal_data_at or now) if personal_data else None,
            credit_bureau_at=(current.credit_bureau_at or now) if credit_bureau else None,
            given_by=account_id if personal_data or credit_bureau else None,
        )
        self.updated_at = now

    def _ensure_editable(self, section: str) -> None:
        if self.status is S.DRAFT:
            return
        request = self.open_info_request
        if self.status is S.INFO_REQUESTED and request and request.allows_field(section):
            return
        raise self._not_editable(section)

    def _not_editable(self, section: str) -> ConflictError:
        return ConflictError(
            "This part of the application cannot be changed now",
            details={"code": "not_editable", "field": section, "status": self.status.value},
        )

    # --- documents ----------------------------------------------------------

    def add_document(
        self,
        *,
        document_id: UUID,
        document_type: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        uploaded_by: UUID,
        now: datetime,
    ) -> Document:
        """Announce an upload; the file goes to storage by a presigned URL."""
        info_request_id: UUID | None = None
        if self.status is S.DRAFT:
            expected = {r.type for r in self.product_terms.required_documents}
            if document_type not in expected | OPTIONAL_DOCUMENT_TYPES:
                raise ValidationError(
                    "This document is not expected for the product",
                    details={"field": "type", "code": "unexpected_document"},
                )
        elif self.status is S.INFO_REQUESTED:
            request = self.open_info_request
            if request is None or document_type not in request.requested_documents:
                raise ValidationError(
                    "The bank did not ask for this document",
                    details={"field": "type", "code": "unexpected_document"},
                )
            info_request_id = request.id
        else:
            raise self._not_editable("documents")
        Document.validate_upload(document_type, filename, content_type, size_bytes)
        document = Document(
            id=document_id,
            type=document_type,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            s3_key=f"applications/{self.id}/{document_id}",
            status=DocumentStatus.PENDING_UPLOAD,
            uploaded_by=uploaded_by,
            created_at=now,
            info_request_id=info_request_id,
        )
        self.documents.append(document)
        self.updated_at = now
        return document

    def confirm_document(
        self, document_id: UUID, actual_size: int, actual_content_type: str, now: datetime
    ) -> Document:
        if self.status not in (S.DRAFT, S.INFO_REQUESTED):
            raise self._not_editable("documents")
        document = self.document(document_id)
        document.confirm_upload(actual_size, actual_content_type, now)
        self.updated_at = now
        return document

    def remove_document(self, document_id: UUID, now: datetime) -> Document:
        document = self.document(document_id)
        request = self.open_info_request
        removable = self.status is S.DRAFT or (
            self.status is S.INFO_REQUESTED
            and request is not None
            and document.info_request_id == request.id
        )
        if not removable:
            raise self._not_editable("documents")
        self.documents.remove(document)
        self.updated_at = now
        return document

    # --- submission ---------------------------------------------------------

    def check_ready(self, legal_form: str | None, has_other_active: bool) -> list[Violation]:
        """Everything that blocks submission; empty — ready. Also feeds the
        "what is left" hint of a draft."""
        violations = [Violation("missing", name) for name in self.request.missing_fields()]
        terms = self.product_terms
        amount = self.request.amount
        if amount is not None and not terms.amount_min <= amount <= terms.amount_max:
            violations.append(
                Violation(
                    "out_of_range",
                    "request.amount",
                    {"min": str(terms.amount_min.amount), "max": str(terms.amount_max.amount)},
                )
            )
        term = self.request.term_months
        if term is not None and not terms.term_min_months <= term <= terms.term_max_months:
            violations.append(
                Violation(
                    "out_of_range",
                    "request.term_months",
                    {"min": terms.term_min_months, "max": terms.term_max_months},
                )
            )
        violations += [
            Violation(error.code, f"product_fields.{error.path}")
            for error in terms.fields_schema.validate(self.product_fields)
        ]
        if terms.needs_collateral(amount) and self.collateral is None:
            violations.append(Violation("missing", "collateral"))
        uploaded_types = {d.type for d in self.uploaded_documents()}
        violations += [
            Violation("missing", f"documents.{document_type}", {"type": document_type})
            for document_type in terms.documents_for(amount, legal_form)
            if document_type not in uploaded_types
        ]
        if self.consents.personal_data_at is None:
            violations.append(Violation("missing", "consents.personal_data"))
        if self.consents.credit_bureau_at is None:
            violations.append(Violation("missing", "consents.credit_bureau"))
        if has_other_active:
            violations.append(Violation("duplicate_active", "product_code"))
        return violations

    def submit(
        self,
        snapshot: OrganizationSnapshot,
        *,
        actor: Actor,
        has_other_active: bool,
        now: datetime,
    ) -> None:
        """`has_other_active` — the company already has a not final application
        on this product (the repository knows, the aggregate decides)."""
        ensure_transition(self.status, S.SUBMITTED)
        if snapshot.organization_id != self.organization_id:
            raise ValueError("Snapshot of another organization")
        violations = self.check_ready(snapshot.legal_form, has_other_active)
        if violations:
            raise ValidationError(
                "Application is not ready to submit",
                details={"violations": [v.as_dict() for v in violations]},
            )
        assert self.request.amount is not None
        assert self.request.term_months is not None and self.request.purpose is not None
        self.org_snapshot = snapshot
        self.submitted_at = now
        self._move(S.SUBMITTED, actor, now)
        self._events.append(
            ApplicationSubmitted(
                occurred_at=now,
                application_id=self.id,
                organization_id=self.organization_id,
                product_code=self.product_code,
                amount=self.request.amount,
                term_months=self.request.term_months,
                purpose=self.request.purpose,
            )
        )

    # --- commands of the process ---------------------------------------------

    def start_review(self, now: datetime, client_stage: str | None = None) -> bool:
        """Repeated command is a no-op (returns False)."""
        if self.status is S.IN_REVIEW:
            return False
        if client_stage is not None:
            self.client_stage = client_stage
        self._move(S.IN_REVIEW, PROCESS, now)
        return True

    def request_info(
        self,
        *,
        info_request_id: UUID,
        fields: tuple[str, ...],
        documents: tuple[str, ...],
        comment: str,
        due_at: datetime | None,
        now: datetime,
    ) -> InfoRequest:
        ensure_transition(self.status, S.INFO_REQUESTED)
        if not fields and not documents:
            raise ValueError("An information request must ask for something")
        info_request = InfoRequest(
            id=info_request_id,
            requested_fields=tuple(fields),
            requested_documents=tuple(documents),
            comment=comment,
            created_at=now,
            due_at=due_at,
        )
        self.info_requests.append(info_request)
        self._move(S.INFO_REQUESTED, PROCESS, now, reason=comment)
        return info_request

    def present_offer(self, offer: Offer, summary: DecisionSummary, now: datetime) -> None:
        ensure_transition(self.status, S.OFFER_READY)
        if offer.is_expired(now):
            raise ValueError("Offer is already expired")
        self.offer = offer
        self.decision_summary = summary
        self._move(S.OFFER_READY, PROCESS, now)

    def reject(self, summary: DecisionSummary, now: datetime) -> None:
        ensure_transition(self.status, S.REJECTED)
        self.decision_summary = summary
        self._expire_open_info_request()
        self._move(S.REJECTED, PROCESS, now, reason=summary.client_explanation)

    def mark_disbursed(self, now: datetime) -> bool:
        if self.status is S.DISBURSED:
            return False
        self._move(S.DISBURSED, PROCESS, now)
        return True

    def set_client_stage(self, client_stage: str | None, now: datetime) -> bool:
        """Stage label from the process (StepCompleted); ignored once closed."""
        if self.is_final or client_stage == self.client_stage:
            return False
        self.client_stage = client_stage
        self.updated_at = now
        return True

    # --- client answers -----------------------------------------------------

    def answer_info_request(self, info_request_id: UUID, actor: Actor, now: datetime) -> None:
        ensure_transition(self.status, S.IN_REVIEW)
        request = self.info_request(info_request_id)
        if not request.is_open:
            raise ConflictError(
                "Information request is already closed", details={"code": "info_request_closed"}
            )
        attached = [d for d in self.uploaded_documents() if d.info_request_id == request.id]
        missing = [t for t in request.requested_documents if t not in {d.type for d in attached}]
        if missing:
            raise ValidationError(
                "Upload the requested documents first",
                details={
                    "violations": [
                        Violation("missing", f"documents.{t}", {"type": t}).as_dict()
                        for t in missing
                    ]
                },
            )
        assert actor.account_id is not None
        request.answer(actor.account_id, now)
        self._move(S.IN_REVIEW, actor, now)
        self._events.append(
            ApplicationInfoProvided(
                occurred_at=now,
                application_id=self.id,
                organization_id=self.organization_id,
                info_request_id=request.id,
                document_ids=tuple(d.id for d in attached),
            )
        )

    def accept_offer(self, actor: Actor, now: datetime) -> None:
        ensure_transition(self.status, S.SIGNING)
        assert self.offer is not None
        if self.offer.is_expired(now):
            raise ConflictError("The offer has expired", details={"code": "offer_expired"})
        self._move(S.SIGNING, actor, now)
        self._events.append(OfferAccepted(**self._ids(now)))

    def decline_offer(self, actor: Actor, now: datetime, reason: str | None = None) -> None:
        ensure_transition(self.status, S.OFFER_DECLINED)
        self._move(S.OFFER_DECLINED, actor, now, reason=reason)
        self._events.append(OfferDeclined(**self._ids(now)))

    def expire_offer(self, now: datetime) -> bool:
        """Background check; a no-op unless the offer is really overdue."""
        if self.status is not S.OFFER_READY or self.offer is None:
            return False
        if not self.offer.is_expired(now):
            return False
        self._move(S.EXPIRED, SYSTEM, now)
        self._events.append(OfferExpired(**self._ids(now)))
        return True

    def sign(self, actor: Actor, now: datetime) -> Signature:
        """Rights (sign within the company) and the step-up password are
        checked by the use case before; the aggregate fixes what was signed."""
        ensure_transition(self.status, S.SIGNED)
        assert self.offer is not None and actor.account_id is not None
        self.signature = Signature(actor.account_id, now, self.offer.fingerprint())
        self._move(S.SIGNED, actor, now)
        self._events.append(ApplicationSigned(**self._ids(now), signed_by=actor.account_id))
        return self.signature

    def cancel(self, actor: Actor, now: datetime, reason: str | None = None) -> None:
        ensure_transition(self.status, S.CANCELLED)
        self._expire_open_info_request()
        self._move(S.CANCELLED, actor, now, reason=reason)
        self._events.append(ApplicationCancelled(**self._ids(now), reason=reason))

    # --- internals ----------------------------------------------------------

    def _move(
        self, target: ApplicationStatus, actor: Actor, now: datetime, reason: str | None = None
    ) -> None:
        ensure_transition(self.status, target)
        source = self.status
        self.status = target
        self.updated_at = now
        if target in FINAL_STATUSES:
            self.closed_at = now
        self.history.append(StatusChange(source.value, target.value, now, actor, reason))
        self._events.append(
            ApplicationStatusChanged(
                **self._ids(now),
                from_status=source.value,
                to_status=target.value,
                client_stage=self.client_stage,
            )
        )

    def _expire_open_info_request(self) -> None:
        request = self.open_info_request
        if request is not None:
            request.status = InfoRequestStatus.EXPIRED

    def _ids(self, now: datetime) -> dict[str, Any]:
        return {
            "occurred_at": now,
            "application_id": self.id,
            "organization_id": self.organization_id,
        }
