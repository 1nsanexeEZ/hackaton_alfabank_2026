"""Applications in any state for domain tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from src.core.domain import Money
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.entities import Document, DocumentStatus, InfoRequest
from src.modules.applications.domain.fields_schema import ProductFieldsSchema
from src.modules.applications.domain.statuses import ApplicationStatus
from src.modules.applications.domain.value_objects import (
    ApplicationNumber,
    CollateralDeclaration,
    Consents,
    DecisionSummary,
    DocumentRequirement,
    LoanRequest,
    Offer,
    OrganizationSnapshot,
    ProductTerms,
)

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
ORG_ID = UUID("00000000-0000-0000-0000-00000000a001")
APPLICANT_ID = UUID("00000000-0000-0000-0000-00000000b001")
INFO_REQUEST_ID = UUID("00000000-0000-0000-0000-00000000c001")

AUTO_FIELDS = {
    "type": "object",
    "properties": {
        "vehicle_type": {"type": "string", "enum": ["car", "truck", "special"]},
        "supplier_name": {"type": "string", "maxLength": 200},
        "price": {"type": "number", "minimum": 1},
    },
    "required": ["vehicle_type", "price"],
}


def terms(**overrides: Any) -> ProductTerms:
    values: dict[str, Any] = {
        "code": "UNSECURED",
        "version": 1,
        "amount_min": Money.of(100_000),
        "amount_max": Money.of(5_000_000),
        "term_min_months": 3,
        "term_max_months": 36,
        "rate_base": Decimal("21.5"),
        "rate_max": Decimal("29.9"),
        "repayment_options": ("annuity",),
        "facility": "term_loan",
        "collateral_required": False,
        "collateral_required_from": None,
        "required_documents": (DocumentRequirement("bank_statement", "Выписка по счёту"),),
        "fields_schema": ProductFieldsSchema(),
        "workflow_code": "standard",
        "auto_decision_limit": Money.of(5_000_000),
    }
    values.update(overrides)
    return ProductTerms(**values)


def draft(product_terms: ProductTerms | None = None) -> CreditApplication:
    return CreditApplication.create_draft(
        id=uuid4(),
        number=ApplicationNumber.issue(2026, 1),
        organization_id=ORG_ID,
        applicant_account_id=APPLICANT_ID,
        product_terms=product_terms or terms(),
        now=NOW,
    )


def uploaded(
    document_type: str = "bank_statement", info_request_id: UUID | None = None
) -> Document:
    document_id = uuid4()
    return Document(
        id=document_id,
        type=document_type,
        filename="statement.csv",
        content_type="text/csv",
        size_bytes=1024,
        s3_key=f"applications/x/{document_id}",
        status=DocumentStatus.UPLOADED,
        uploaded_by=APPLICANT_ID,
        created_at=NOW,
        uploaded_at=NOW,
        info_request_id=info_request_id,
    )


def ready_draft(product_terms: ProductTerms | None = None) -> CreditApplication:
    """A draft that passes every submission check."""
    application = draft(product_terms)
    application.request = LoanRequest(Money.of(3_000_000), 24, "working_capital")
    application.consents = Consents(NOW, NOW, APPLICANT_ID)
    application.documents.append(uploaded())
    return application


def snapshot(organization_id: UUID = ORG_ID, legal_form: str = "LLC") -> OrganizationSnapshot:
    return OrganizationSnapshot(
        organization_id=organization_id,
        legal_form=legal_form,
        taken_at=NOW,
        data={"inn": "7701158817", "name": "ООО «Ромашка»"},
    )


def offer(expires_at: datetime | None = None) -> Offer:
    return Offer(
        kind="as_requested",
        amount=Money.of(3_000_000),
        term_months=24,
        rate=Decimal("23.5"),
        monthly_payment=Money.of("158000.00"),
        schedule_type="annuity",
        conditions=("Без залога",),
        expires_at=expires_at or NOW + timedelta(days=7),
        decision_id=uuid4(),
    )


def summary(outcome: str = "APPROVE") -> DecisionSummary:
    return DecisionSummary(outcome=outcome, client_explanation="Заявка одобрена")


def in_status(status: ApplicationStatus) -> CreditApplication:
    """Complete application already in `status`, with whatever that status
    implies: an offer, an open information request with its answer uploaded."""
    application = ready_draft()
    application.status = status
    application.pull_events()
    if status is not ApplicationStatus.DRAFT:
        application.org_snapshot = snapshot()
        application.submitted_at = NOW
    application.offer = offer()
    application.decision_summary = summary()
    application.info_requests.append(
        InfoRequest(
            id=INFO_REQUEST_ID,
            requested_fields=("collateral",),
            requested_documents=("financial_statement",),
            comment="Нужна бухгалтерская отчётность",
            created_at=NOW,
            due_at=None,
        )
    )
    application.documents.append(uploaded("financial_statement", INFO_REQUEST_ID))
    application.collateral = CollateralDeclaration(
        "equipment", "Станок", Money.of(1_000_000), "self"
    )
    return application
