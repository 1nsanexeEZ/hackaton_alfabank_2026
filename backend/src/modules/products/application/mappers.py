"""Domain objects -> contract DTOs (src/modules/products/facade.py)."""

import copy
from typing import cast
from uuid import UUID

from src.modules.products.domain.calculator import PaymentSchedule
from src.modules.products.domain.product import CreditProduct
from src.modules.products.domain.recommender import Recommendation
from src.modules.products.domain.value_objects import (
    LEGAL_FORMS,
    PURPOSES,
    DocumentRequirement,
    EligibilityCheck,
    EligibilityReason,
    ProductTerms,
    SupportProgram,
    ordered,
)
from src.modules.products.facade import (
    CollateralKind,
    EligibilityCheckDTO,
    EligibilityReasonDTO,
    Facility,
    Guarantee,
    PaymentDTO,
    PaymentScheduleDTO,
    ProductDTO,
    ProductStatus,
    ProductTermsDTO,
    Purpose,
    RecommendationDTO,
    Repayment,
    RequiredDocumentDTO,
    SupportProgramDTO,
)


def document_dto(document: DocumentRequirement) -> RequiredDocumentDTO:
    return RequiredDocumentDTO(
        type=document.type,
        title=document.title,
        required_from_amount=None
        if document.required_from is None
        else document.required_from.amount,
        legal_forms=ordered(document.legal_forms, LEGAL_FORMS),
    )


def support_program_dto(program: SupportProgram) -> SupportProgramDTO:
    return SupportProgramDTO(
        code=program.code,
        name=program.name,
        rate_cap=program.rate_cap,
        msp_registry_required=program.msp_registry_required,
        okved_whitelist=tuple(sorted(program.okved_whitelist)),
    )


def product_dto(product: CreditProduct) -> ProductDTO:
    security = product.security
    rules = product.eligibility
    program = product.support_program
    return ProductDTO(
        code=product.code.value,
        frontend_id=product.frontend_id,
        version=product.version,
        name=product.name,
        short_description=product.short_description,
        description_plain=product.description_plain,
        purposes=cast(tuple[Purpose, ...], ordered(product.purposes, PURPOSES)),
        facility=cast(Facility, product.facility),
        repayment_options=cast(tuple[Repayment, ...], product.repayment_options),
        amount_min=product.amount.min.amount,
        amount_max=product.amount.max.amount,
        term_min_months=product.term.min_months,
        term_max_months=product.term.max_months,
        rate_base=product.rate.base,
        rate_max=product.rate.max,
        collateral_kind=cast(CollateralKind, security.collateral),
        collateral_required_from=None
        if security.required_from is None
        else security.required_from.amount,
        collateral_types=security.collateral_types,
        guarantee=cast(Guarantee, security.guarantee),
        target_use_confirmation=product.target_use_confirmation,
        support_program=None if program is None else support_program_dto(program),
        min_business_age_months=rules.min_business_age_months,
        allowed_legal_forms=ordered(rules.allowed_legal_forms, LEGAL_FORMS),
        min_annual_revenue=None
        if rules.min_annual_revenue is None
        else rules.min_annual_revenue.amount,
        required_documents=tuple(document_dto(d) for d in product.required_documents),
        application_fields_schema=copy.deepcopy(dict(product.application_fields_schema)),
        workflow_code=product.processing.workflow_code,
        auto_decision_limit=product.processing.auto_decision_limit.amount,
        status=cast(ProductStatus, product.status.value),
        startup_only=rules.startup_only,
    )


def terms_dto(terms: ProductTerms) -> ProductTermsDTO:
    return ProductTermsDTO(
        code=terms.code,
        version=terms.version,
        amount_min=terms.amount.min.amount,
        amount_max=terms.amount.max.amount,
        term_min_months=terms.term.min_months,
        term_max_months=terms.term.max_months,
        rate_base=terms.rate.base,
        rate_max=terms.rate.max,
        repayment_options=cast(tuple[Repayment, ...], terms.repayment_options),
        facility=cast(Facility, terms.facility),
        collateral_required=terms.collateral_required,
        collateral_required_from=None
        if terms.collateral_required_from is None
        else terms.collateral_required_from.amount,
        required_documents=tuple(document_dto(d) for d in terms.required_documents),
        application_fields_schema=copy.deepcopy(dict(terms.application_fields_schema)),
        workflow_code=terms.workflow_code,
        auto_decision_limit=terms.auto_decision_limit.amount,
    )


def reason_dto(reason: EligibilityReason) -> EligibilityReasonDTO:
    return EligibilityReasonDTO(code=reason.code, passed=reason.passed, message=reason.message)


def check_dto(check: EligibilityCheck, organization_id: UUID) -> EligibilityCheckDTO:
    return EligibilityCheckDTO(
        product_code=check.product_code,
        organization_id=organization_id,
        eligible=check.eligible,
        reasons=tuple(reason_dto(r) for r in check.reasons),
    )


def recommendation_dto(recommendation: Recommendation) -> RecommendationDTO:
    return RecommendationDTO(
        product=product_dto(recommendation.product),
        rank=recommendation.rank,
        eligible=recommendation.eligible,
        reasons=tuple(reason_dto(r) for r in recommendation.reasons),
        estimated_monthly_payment=recommendation.monthly_payment_from.amount,
    )


def schedule_dto(schedule: PaymentSchedule) -> PaymentScheduleDTO:
    return PaymentScheduleDTO(
        amount=schedule.amount.amount,
        term_months=schedule.term_months,
        rate=schedule.rate,
        repayment=cast(Repayment, schedule.repayment),
        monthly_payment=schedule.monthly_payment.amount,
        total_interest=schedule.total_interest.amount,
        total_paid=schedule.total_paid.amount,
        payments=tuple(
            PaymentDTO(
                number=p.number,
                due_date=None,
                principal=p.principal.amount,
                interest=p.interest.amount,
                total=p.total.amount,
                balance_after=p.balance_after.amount,
            )
            for p in schedule.payments
        ),
    )
