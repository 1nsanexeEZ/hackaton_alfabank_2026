"""CreditProduct — the aggregate root of the module.

A kind of credit is not one enum but a combination: purpose × facility ×
repayment schedule × security × state support. The product sets the frames
(amount, term, rate), who may get it and what the application must contain;
the decision on an application is taken elsewhere.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.core.domain import Money
from src.core.exceptions.exceptions import InvalidStatusTransitionError
from src.modules.products.domain import texts
from src.modules.products.domain.errors import ProductNotAvailableError
from src.modules.products.domain.value_objects import (
    FACILITIES,
    PURPOSES,
    REPAYMENTS,
    AmountRange,
    BorrowerProfile,
    DocumentRequirement,
    Eligibility,
    EligibilityCheck,
    EligibilityReason,
    ProcessingProfile,
    ProductCode,
    ProductTerms,
    RateRange,
    SecurityRequirement,
    SupportProgram,
    TermRange,
    invalid,
)
from src.modules.products.facade import STARTUP_AGE_MONTHS

_FRONTEND_ID = re.compile(r"^[a-z][a-z0-9-]*$")


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(eq=False)
class CreditProduct:
    code: ProductCode
    version: int
    status: ProductStatus
    name: str
    short_description: str
    description_plain: str
    # Card id in the frontend catalog (`unsecured`, `credit-line`).
    frontend_id: str
    purposes: frozenset[str]
    facility: str
    # The first option is the default schedule.
    repayment_options: tuple[str, ...]
    amount: AmountRange
    term: TermRange
    rate: RateRange
    security: SecurityRequirement
    eligibility: Eligibility
    processing: ProcessingProfile
    required_documents: tuple[DocumentRequirement, ...] = ()
    support_program: SupportProgram | None = None
    # Money goes to a stated target (a vehicle, a property, other loans).
    target_use_confirmation: bool = False
    # JSON Schema of the extra application form fields.
    application_fields_schema: Mapping[str, Any] = field(default_factory=dict)
    # Position in the catalog.
    sort_order: int = 0

    def __post_init__(self) -> None:
        self.status = ProductStatus(self.status)
        self.purposes = frozenset(self.purposes)
        self.repayment_options = tuple(self.repayment_options)
        self.required_documents = tuple(self.required_documents)
        self._check_invariants()

    def _check_invariants(self) -> None:
        if self.version < 1:
            raise invalid("version", "not_positive", "Version starts with 1")
        if not self.name.strip() or not self.short_description.strip():
            raise invalid("name", "missing", "Product needs a name and a short description")
        if not _FRONTEND_ID.match(self.frontend_id):
            raise invalid("frontend_id", "bad_format", "Invalid frontend id")
        if not self.purposes:
            raise invalid("purposes", "missing", "Product needs at least one purpose")
        if not self.purposes <= set(PURPOSES):
            raise invalid("purposes", "unknown", "Unknown credit purpose")
        if self.facility not in FACILITIES:
            raise invalid("facility", "unknown", "Unknown facility")
        if not self.repayment_options:
            raise invalid("repayment_options", "missing", "Product needs a repayment schedule")
        if not set(self.repayment_options) <= set(REPAYMENTS):
            raise invalid("repayment_options", "unknown", "Unknown repayment schedule")
        if len(set(self.repayment_options)) != len(self.repayment_options):
            raise invalid("repayment_options", "duplicate", "Repayment schedules repeat")
        if self.amount.max < self.processing.auto_decision_limit:
            raise invalid(
                "auto_decision_limit", "above_max", "Auto decision limit is above the maximum"
            )
        threshold = self.security.required_from
        if threshold is not None and not self.amount.contains(threshold):
            raise invalid(
                "collateral_required_from", "out_of_range", "Threshold is out of the amount range"
            )
        program = self.support_program
        if program is not None and not self.rate.contains(program.rate_cap):
            raise invalid(
                "support_program.rate_cap", "out_of_range", "Rate cap is out of the rate range"
            )
        types = [document.type for document in self.required_documents]
        if len(set(types)) != len(types):
            raise invalid("required_documents", "duplicate", "Document types repeat")
        schema_type = self.application_fields_schema.get("type", "object")
        if self.application_fields_schema and schema_type != "object":
            raise invalid("application_fields_schema", "not_object", "Fields schema is an object")

    # --- status -------------------------------------------------------------

    @property
    def is_selectable(self) -> bool:
        return self.status == ProductStatus.ACTIVE

    def ensure_selectable(self) -> None:
        if not self.is_selectable:
            raise ProductNotAvailableError(
                details={"code": self.code.value, "status": self.status.value}
            )

    def activate(self) -> None:
        if self.status != ProductStatus.DRAFT:
            raise InvalidStatusTransitionError(
                details={"from": self.status.value, "to": ProductStatus.ACTIVE.value}
            )
        self.status = ProductStatus.ACTIVE

    def archive(self) -> None:
        """Archived products stay readable (old applications refer to them)
        but can't be chosen; changed terms are a new version."""
        if self.status == ProductStatus.ARCHIVED:
            raise InvalidStatusTransitionError(
                details={"from": self.status.value, "to": ProductStatus.ARCHIVED.value}
            )
        self.status = ProductStatus.ARCHIVED

    # --- terms ----------------------------------------------------------------

    @property
    def client_rate(self) -> RateRange:
        """Rates the client may be offered: a support program caps the maximum."""
        if self.support_program is None:
            return self.rate
        return RateRange(self.rate.base, min(self.rate.max, self.support_program.rate_cap))

    @property
    def default_repayment(self) -> str:
        return self.repayment_options[0]

    def serves(self, purpose: str) -> bool:
        return purpose in self.purposes

    def fits(self, amount: Money, term_months: int) -> bool:
        return self.amount.contains(amount) and self.term.contains(term_months)

    def needs_collateral(self, amount: Money | None) -> bool:
        return self.security.needs_collateral(amount)

    def documents_for(
        self, amount: Money | None, legal_form: str | None
    ) -> tuple[DocumentRequirement, ...]:
        return tuple(d for d in self.required_documents if d.applies(amount, legal_form))

    def requires_manual_review(self, amount: Money) -> bool:
        return self.processing.requires_manual_review(amount)

    def snapshot(self) -> ProductTerms:
        """Terms copied into a new application: only an active product can be chosen."""
        self.ensure_selectable()
        return ProductTerms(
            code=self.code.value,
            version=self.version,
            amount=self.amount,
            term=self.term,
            rate=self.client_rate,
            repayment_options=self.repayment_options,
            facility=self.facility,
            collateral_required=self.security.collateral == "required",
            collateral_required_from=self.security.required_from,
            required_documents=self.required_documents,
            application_fields_schema=self.application_fields_schema,
            workflow_code=self.processing.workflow_code,
            auto_decision_limit=self.processing.auto_decision_limit,
        )

    # --- eligibility ----------------------------------------------------------

    def check_eligibility(self, borrower: BorrowerProfile) -> EligibilityCheck:
        """Every condition gives a reason, passed or not, in words for the bank
        employee. Registry status and data verification don't block: they are
        stop factors of the decision, here they are only noted."""
        rules = self.eligibility
        reasons = [
            _legal_form_reason(rules, borrower),
            _business_age_reason(rules, borrower),
        ]
        if rules.min_annual_revenue is not None:
            reasons.append(_revenue_reason(rules.min_annual_revenue, borrower))
        if rules.startup_only:
            reasons.append(_startup_reason(borrower))
        if self.support_program is not None:
            reasons += _support_program_reasons(self.support_program, borrower)
        if borrower.registry_status != "active":
            status = texts.REGISTRY_STATUS_TITLES.get(
                borrower.registry_status, borrower.registry_status
            )
            reasons.append(
                EligibilityReason(
                    "registry_status",
                    True,
                    f"По реестру компания в статусе «{status}» — "
                    "банк учтёт это при рассмотрении заявки",
                )
            )
        if not borrower.verified:
            reasons.append(
                EligibilityReason(
                    "verification",
                    True,
                    "Данные компании не совпадают с реестром или ещё не сверены — "
                    "банк уточнит их при рассмотрении заявки",
                )
            )
        return EligibilityCheck(self.code.value, tuple(reasons))


def _legal_form_reason(rules: Eligibility, borrower: BorrowerProfile) -> EligibilityReason:
    form = texts.LEGAL_FORM_TITLES.get(borrower.legal_form, borrower.legal_form)
    if borrower.legal_form in rules.allowed_legal_forms:
        return EligibilityReason("legal_form", True, f"Форма бизнеса {form} подходит")
    allowed = texts.legal_forms(rules.allowed_legal_forms)
    return EligibilityReason(
        "legal_form", False, f"Продукт доступен только для {allowed}, а у вас {form}"
    )


def _business_age_reason(rules: Eligibility, borrower: BorrowerProfile) -> EligibilityReason:
    need = texts.from_months(rules.min_business_age_months)
    age = borrower.business_age_months
    if age >= rules.min_business_age_months:
        return EligibilityReason(
            "business_age", True, f"Срок работы подходит: нужно {need}, у вас {age}"
        )
    return EligibilityReason("business_age", False, f"Нужно {need} работы, у вас {age}")


def is_startup(borrower: BorrowerProfile) -> bool:
    return borrower.business_age_months < STARTUP_AGE_MONTHS or borrower.annual_revenue is None


def _startup_reason(borrower: BorrowerProfile) -> EligibilityReason:
    if is_startup(borrower):
        return EligibilityReason(
            "startup", True, "Компания без оборотов и годовой отчётности — продукт для неё"
        )
    return EligibilityReason(
        "startup",
        False,
        f"Продукт для компаний младше {texts.from_months(STARTUP_AGE_MONTHS)} или без "
        "годовой отчётности; у вас есть обороты — подойдут другие продукты",
    )


def _revenue_reason(minimum: Money, borrower: BorrowerProfile) -> EligibilityReason:
    need = texts.money(minimum)
    revenue = borrower.annual_revenue
    if revenue is None:
        return EligibilityReason(
            "annual_revenue",
            False,
            f"Нужна выручка от {need} в год, а данных о выручке нет — добавьте отчёт за год",
        )
    have = texts.money(revenue)
    if revenue >= minimum:
        return EligibilityReason(
            "annual_revenue", True, f"Выручка подходит: нужно от {need} в год, у вас {have}"
        )
    return EligibilityReason(
        "annual_revenue", False, f"Нужна выручка от {need} в год, у вас {have}"
    )


def _support_program_reasons(
    program: SupportProgram, borrower: BorrowerProfile
) -> list[EligibilityReason]:
    reasons: list[EligibilityReason] = []
    if program.msp_registry_required:
        if borrower.in_msp_registry is None:
            reasons.append(
                EligibilityReason(
                    "msp_registry",
                    True,
                    "Включение в реестр МСП проверим по реестру при рассмотрении заявки",
                )
            )
        elif borrower.in_msp_registry:
            reasons.append(EligibilityReason("msp_registry", True, "Компания в реестре МСП"))
        else:
            reasons.append(
                EligibilityReason(
                    "msp_registry", False, "Программа только для компаний из реестра МСП"
                )
            )
    if program.okved_whitelist:
        okved = borrower.okved_class
        if program.covers(okved):
            message = f"ОКВЭД {okved} входит в программу господдержки «{program.name}»"
        else:
            message = f"ОКВЭД {okved} не входит в программу господдержки «{program.name}»"
        reasons.append(EligibilityReason("okved", program.covers(okved), message))
    return reasons
