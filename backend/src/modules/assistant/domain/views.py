"""What the assistant knows about an application, a decision and a product.

The views repeat the client side of the neighbours' facades field by field:
`ClientDecisionView` is `decision.ClientDecisionDTO`, `ApplicationView` is the
client-safe part of `applications.ApplicationCardDTO`, `ProductView` is
`products.ProductDTO` without the routing internals. There are no fields for
the score, scorecard factors, reason codes, rule trace, credit bureau data or
the company's name and INN: what is not here can't reach a prompt.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

Outcome = Literal["APPROVE", "COUNTER_OFFER", "REQUEST_INFO", "MANUAL_REVIEW", "REJECT"]


@dataclass(frozen=True, slots=True)
class DecisionTermsView:
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: str
    conditions: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RequestedInfoView:
    fields: tuple[str, ...]
    documents: tuple[str, ...]
    comment: str


@dataclass(frozen=True, slots=True)
class ClientDecisionView:
    outcome: Outcome
    terms: DecisionTermsView | None
    alternative_product_code: str | None
    client_explanation: str
    improvement_hints: tuple[str, ...]
    requested_info: RequestedInfoView | None


@dataclass(frozen=True, slots=True)
class LoanRequestView:
    amount: Decimal
    term_months: int
    purpose: str
    # Typed by the client: passed to a local model only, as quoted data.
    purpose_comment: str | None = None


@dataclass(frozen=True, slots=True)
class InfoRequestView:
    requested_fields: tuple[str, ...]
    requested_documents: tuple[str, ...]
    comment: str
    due_at: datetime | None
    status: Literal["open", "answered", "expired"]


@dataclass(frozen=True, slots=True)
class ApplicationView:
    id: UUID
    number: str
    organization_id: UUID
    product_code: str
    status: str
    client_stage: str | None
    request: LoanRequestView | None
    info_requests: tuple[InfoRequestView, ...]
    updated_at: datetime
    # The viewer's right to sign in the application's company.
    viewer_can_sign: bool = False


@dataclass(frozen=True, slots=True)
class RequiredDocumentView:
    type: str
    title: str
    required_from_amount: Decimal | None = None
    legal_forms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductView:
    code: str
    name: str
    short_description: str
    description_plain: str
    purposes: tuple[str, ...]
    facility: str
    repayment_options: tuple[str, ...]
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal
    collateral_kind: str
    collateral_types: tuple[str, ...]
    min_business_age_months: int
    min_annual_revenue: Decimal | None
    required_documents: tuple[RequiredDocumentView, ...]
    support_program_name: str | None = None
    support_rate_cap: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PaymentView:
    amount: Decimal
    term_months: int
    rate: Decimal
    repayment: str
    monthly_payment: Decimal
    total_interest: Decimal
    total_paid: Decimal


@dataclass(frozen=True, slots=True)
class Viewer:
    """Who asks. `organization_ids` — the companies a client is a member of;
    None — bank staff, not limited to companies."""

    account_id: UUID
    organization_ids: frozenset[UUID] | None

    def may_see(self, organization_id: UUID) -> bool:
        return self.organization_ids is None or organization_id in self.organization_ids
