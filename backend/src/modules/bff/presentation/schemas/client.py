"""Client screens as the frontend gets them.

Client screens list every field explicitly: a model is read from a screen DTO
and the facade DTOs inside it by attribute, so only what is declared here
leaves the bank — never the score, scoring factors, rule trace, reason codes or
credit bureau data."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.bff.application.dto.products import CalculationDTO
from src.modules.bff.domain.enums import ClientStatus, TodoKind
from src.modules.products.facade import Repayment


class ClientModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- shared client blocks ---------------------------------------------------


class OrganizationBrief(ClientModel):
    id: UUID
    name: str
    inn: str
    legal_form: str
    my_role: str
    my_permissions: list[str]


class CurrentOrganization(OrganizationBrief):
    verification_status: str
    registry_status: str
    # startup — younger than 6 months or no annual report: the founder's prescreen and the
    # startup product instead of pre-approval.
    segment: Literal["established", "startup"] = "established"


class ApplicationRow(ClientModel):
    id: UUID
    number: str
    product_code: str
    product_name: str
    amount: Decimal | None
    term_months: int | None
    status: str
    client_status: ClientStatus
    client_stage: str | None
    action_required: str
    offer_amount: Decimal | None
    offer_rate: Decimal | None
    submitted_at: datetime | None
    updated_at: datetime


class FeedItem(ClientModel):
    id: UUID
    type: str
    title: str
    body: str
    link: str | None
    priority: str
    action_required: bool
    organization_id: UUID | None
    application_id: UUID | None
    created_at: datetime
    read_at: datetime | None


# --- dashboard ----------------------------------------------------------------


class Counters(ClientModel):
    active_applications: int
    action_required_count: int
    pre_approved_max_amount: Decimal | None
    pre_approved_rate_from: Decimal | None
    last_activity_at: datetime | None


class PreApprovedOffer(ClientModel):
    product_code: str
    product_name: str | None
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    valid_until: date


class TodoItem(ClientModel):
    application_id: UUID
    number: str
    kind: TodoKind
    title: str


class Feed(ClientModel):
    unread: int
    items: list[FeedItem]


class NewsItem(ClientModel):
    id: UUID
    title: str
    body: str
    published_at: datetime
    relevance: list[str]


class PrescreenReason(ClientModel):
    code: str
    passed: bool
    message: str


class FounderPrescreen(ClientModel):
    # failed — «отказ (стартап)»: the client reads `reasons[].message`.
    status: Literal["passed", "failed"]
    founder_name: str
    checked_at: datetime
    valid_until: datetime
    # False — expired: run a new one before a STARTUP application.
    valid: bool
    reasons: list[PrescreenReason]


class ProjectReason(ClientModel):
    code: str
    passed: bool
    message: str


class ProjectAssessment(ClientModel):
    """passed — «вам предодобрен кредит» `product_code` до `max_amount`, it is also in
    `pre_approved`; failed — the client reads `reasons[].message`. No figures of the model:
    they would give the thresholds away."""

    status: Literal["passed", "failed"]
    product_code: str
    max_amount: Decimal | None
    # Below `startup.business_plan_revision` — the plan was changed after the assessment.
    plan_revision: int
    checked_at: datetime
    valid_until: datetime
    # False — expired: run a new one.
    valid: bool
    reasons: list[ProjectReason]


class StartupBlock(ClientModel):
    # None — not run yet: POST /organizations/{id}/founder-prescreen.
    prescreen: FounderPrescreen | None
    # None — not filled in yet: PUT /organizations/{id}/business-plan.
    business_plan_revision: int | None = None
    # None — not run yet: POST /organizations/{id}/project-assessment.
    project: ProjectAssessment | None = None


class Dashboard(ClientModel):
    # No companies yet: the frontend offers to add one.
    onboarding: bool
    organization: CurrentOrganization | None
    organizations: list[OrganizationBrief]
    counters: Counters | None
    # A startup has no turnover to pre-approve on: only the offer by its project assessment.
    pre_approved: list[PreApprovedOffer]
    active_applications: list[ApplicationRow]
    todo: list[TodoItem]
    feed: Feed
    news: list[NewsItem]
    degraded: list[str]
    # Only for organization.segment = startup.
    startup: StartupBlock | None = None


# --- applications list --------------------------------------------------------


class ApplicationList(ClientModel):
    items: list[ApplicationRow]
    total: int


# --- client application card -------------------------------------------------


class OrganizationRef(ClientModel):
    id: UUID
    name: str
    inn: str


class ProductInfo(ClientModel):
    code: str
    name: str | None
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal


class LoanRequest(ClientModel):
    amount: Decimal
    term_months: int
    purpose: str
    purpose_comment: str | None


class Collateral(ClientModel):
    type: str
    description: str
    declared_value: Decimal
    owner: str


class Document(ClientModel):
    id: UUID
    type: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    uploaded_at: datetime | None
    info_request_id: UUID | None
    review_comment: str | None


class InfoRequest(ClientModel):
    id: UUID
    requested_fields: list[str]
    requested_documents: list[str]
    comment: str
    created_at: datetime
    due_at: datetime | None
    status: str
    answered_at: datetime | None


class Offer(ClientModel):
    kind: str
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: str
    conditions: list[str]
    expires_at: datetime


class DecisionTerms(ClientModel):
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: str
    conditions: list[str]
    expires_at: datetime


class RequestedInfo(ClientModel):
    fields: list[str]
    documents: list[str]
    comment: str


class ClientDecision(ClientModel):
    outcome: str
    terms: DecisionTerms | None = None
    alternative_product_code: str | None
    client_explanation: str
    improvement_hints: list[str]
    requested_info: RequestedInfo | None = None


class ClientTimelineEntry(ClientModel):
    at: datetime
    kind: str
    title: str


class HeadConsent(ClientModel):
    # The head by the state registry gives their own consent to the request of
    # their credit history; without it the bank skips that check.
    required: bool
    given: bool
    given_at: datetime | None
    head_name: str


class ApplicationConsents(ClientModel):
    # None — the registry names no head of the company.
    head_credit_bureau: HeadConsent | None


class ClientApplicationCard(ClientModel):
    id: UUID
    number: str
    organization: OrganizationRef | None
    product: ProductInfo
    status: str
    client_status: ClientStatus
    client_stage: str | None
    request: LoanRequest | None
    product_fields: dict[str, Any]
    collateral: Collateral | None
    documents: list[Document]
    # The open request for information, if the bank is waiting for an answer.
    info_request: InfoRequest | None
    offer: Offer | None
    decision: ClientDecision | None
    consents: ApplicationConsents
    timeline: list[ClientTimelineEntry]
    feed: list[FeedItem]
    available_actions: list[str]
    my_permissions: list[str]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    closed_at: datetime | None
    degraded: list[str]


# --- product matching ---------------------------------------------------------


class EligibilityReason(ClientModel):
    code: str
    passed: bool
    message: str


class Recommendation(ClientModel):
    product_code: str
    product_name: str
    short_description: str
    rank: int
    # best — the first product that fits; unavailable — the company does not fit.
    fit: str
    eligible: bool | None
    eligibility: list[EligibilityReason]
    rate_from: Decimal
    amount_max: Decimal
    term_max_months: int
    payment_from: Decimal | None
    pre_approved_max: Decimal | None


class Recommendations(ClientModel):
    items: list[Recommendation]
    degraded: list[str]


# --- calculator with the pre-approval -----------------------------------------


class PersonalCalculateBody(BaseModel):
    """As for `POST /products/{code}/calculate`, but without the rate: the bank sets it."""

    model_config = ConfigDict(extra="forbid")

    amount: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
    term_months: Annotated[int, Field(ge=1, le=360)]
    # The default schedule of the product when omitted.
    repayment: Repayment | None = None

    def to_dto(self) -> CalculationDTO:
        return CalculationDTO(
            amount=self.amount, term_months=self.term_months, repayment=self.repayment
        )


class Payment(ClientModel):
    number: int
    due_date: date | None
    principal: Decimal
    interest: Decimal
    total: Decimal
    balance_after: Decimal


class PaymentSchedule(ClientModel):
    amount: Decimal
    term_months: int
    rate: Decimal
    repayment: Repayment
    # The first payment for non-annuity schedules.
    monthly_payment: Decimal
    total_interest: Decimal
    total_paid: Decimal
    payments: list[Payment]


class PreApprovedTerms(ClientModel):
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    valid_until: date
    # estimate — a conservative estimate without the credit bureau; full — after a check.
    basis: Literal["estimate", "full"]


class Suggestion(ClientModel):
    amount: Decimal
    term_months: int
    monthly_payment: Decimal


class PersonalSchedule(ClientModel):
    # At the pre-approved rate; at the base rate of the product without a pre-approval.
    schedule: PaymentSchedule
    pre_approved: PreApprovedTerms | None
    # None — nothing is pre-approved for this product, nothing to compare with.
    within_pre_approved: bool | None
    eligible: bool
    # Eligibility reasons and what is above the pre-approved terms.
    reasons: list[EligibilityReason]
    # The request cut to the pre-approved terms; None when it fits or nothing is pre-approved.
    suggestion: Suggestion | None
    degraded: list[str]
