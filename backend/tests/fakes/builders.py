"""DTO builders on demo data (seed/demo_data.py): one place to get a valid
snapshot, product or card in a test, overriding only what the test is about."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from seed.demo_data import COMPANIES_BY_CODE, FINANCIALS_BY_CODE
from src.applications.facade import ApplicationCardDTO, LoanRequestDTO, ScoringInputDTO
from src.clients.facade import FinancialReportDTO, OrganizationSnapshotDTO
from src.products.facade import ProductDTO, ProductTermsDTO, RequiredDocumentDTO

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def organization_snapshot(
    code: str = "romashka", organization_id: UUID | None = None, **overrides: Any
) -> OrganizationSnapshotDTO:
    company = COMPANIES_BY_CODE[code]
    finance = FINANCIALS_BY_CODE[code]
    reports = [
        FinancialReportDTO(
            period_year=NOW.year - 1,
            period_quarter=None,
            source="declared",
            revenue=finance.declared_revenue,
            expenses=finance.declared_expenses,
        )
    ]
    if finance.declared_revenue_previous_year is not None:
        reports.append(
            FinancialReportDTO(
                period_year=NOW.year - 2,
                period_quarter=None,
                source="declared",
                revenue=finance.declared_revenue_previous_year,
            )
        )
    head = company.registry_head
    snapshot = OrganizationSnapshotDTO(
        id=organization_id or uuid4(),
        inn=company.inn,
        ogrn=company.ogrn,
        kpp=company.kpp,
        legal_form=company.legal_form,
        name=company.name,
        registered_at=(NOW - timedelta(days=round(company.registered_months_ago * 30.44))).date(),
        business_age_months=company.registered_months_ago,
        okved_main=company.okved_main,
        okved_extra=(),
        region_code="77",
        tax_regime="usn" if company.legal_form == "IE" else "osn",
        employees_count=12,
        registry_status=company.registry_status,
        verification_status="mismatch" if code == "vector" else "verified",
        discrepancies=(),
        head_name=" ".join(p for p in (head.last_name, head.first_name, head.middle_name) if p),
        financial_reports=tuple(reports),
        snapshot_at=NOW,
    )
    return replace(snapshot, **overrides)


def product(code: str = "UNSECURED", **overrides: Any) -> ProductDTO:
    dto = ProductDTO(
        code=code,
        frontend_id=code.lower().replace("_", "-"),
        version=1,
        name=f"Кредит {code}",
        short_description="Тестовый продукт",
        description_plain="Тестовый продукт",
        purposes=("working_capital",),
        facility="term_loan",
        repayment_options=("annuity", "differentiated"),
        amount_min=Decimal("100000"),
        amount_max=Decimal("5000000"),
        term_min_months=3,
        term_max_months=36,
        rate_base=Decimal("21.5"),
        rate_max=Decimal("29.9"),
        collateral_kind="none",
        collateral_required_from=None,
        collateral_types=(),
        guarantee="none",
        target_use_confirmation=False,
        support_program=None,
        min_business_age_months=6,
        allowed_legal_forms=("LLC", "IE", "JSC"),
        min_annual_revenue=None,
        required_documents=(RequiredDocumentDTO(type="bank_statement", title="Выписка по счёту"),),
        application_fields_schema={},
        workflow_code="standard",
        auto_decision_limit=Decimal("5000000"),
        status="active",
    )
    return replace(dto, **overrides)


def product_terms(source: ProductDTO | None = None, **overrides: Any) -> ProductTermsDTO:
    p = source or product()
    terms = ProductTermsDTO(
        code=p.code,
        version=p.version,
        amount_min=p.amount_min,
        amount_max=p.amount_max,
        term_min_months=p.term_min_months,
        term_max_months=p.term_max_months,
        rate_base=p.rate_base,
        rate_max=p.rate_max,
        repayment_options=p.repayment_options,
        facility=p.facility,
        collateral_required=p.collateral_kind == "required",
        collateral_required_from=p.collateral_required_from,
        required_documents=p.required_documents,
        application_fields_schema=p.application_fields_schema,
        workflow_code=p.workflow_code,
        auto_decision_limit=p.auto_decision_limit,
    )
    return replace(terms, **overrides)


def application_card(
    organization: OrganizationSnapshotDTO | None = None,
    amount: Decimal = Decimal("3000000"),
    term_months: int = 24,
    status: str = "in_review",
    **overrides: Any,
) -> ApplicationCardDTO:
    org = organization or organization_snapshot()
    card = ApplicationCardDTO(
        id=uuid4(),
        number="КР-2026-000001",
        organization_id=org.id,
        applicant_account_id=uuid4(),
        product_code="UNSECURED",
        product_terms=product_terms(),
        request=LoanRequestDTO(amount=amount, term_months=term_months, purpose="working_capital"),
        product_fields={},
        collateral=None,
        consents=None,
        org_snapshot=org,
        status=status,  # type: ignore[arg-type]
        client_stage=None,
        documents=(),
        info_requests=(),
        offer=None,
        decision_summary=None,
        history=(),
        version=1,
        created_at=NOW,
        updated_at=NOW,
        submitted_at=NOW,
    )
    return replace(card, **overrides)


def scoring_input(card: ApplicationCardDTO | None = None, **overrides: Any) -> ScoringInputDTO:
    c = card or application_card()
    assert c.request is not None and c.org_snapshot is not None
    dto = ScoringInputDTO(
        application_id=c.id,
        organization_id=c.organization_id,
        product_code=c.product_code,
        request=c.request,
        organization=c.org_snapshot,
        product_terms=c.product_terms,
        collateral=c.collateral,
        statement_document_ids=(),
        credit_bureau_consent_at=NOW,
        submitted_at=c.submitted_at or NOW,
    )
    return replace(dto, **overrides)


def today() -> date:
    return NOW.date()
