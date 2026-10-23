"""The applications list and the client card. Blocks copied from the
applications, projector, decision and notifications facades travel as their
DTOs: the response schema reads only the fields the client may see."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from src.modules.applications.facade import (
    CollateralDTO,
    DecisionSummaryDTO,
    DocumentDTO,
    InfoRequestDTO,
    LoanRequestDTO,
    OfferDTO,
)
from src.modules.bff.domain.client_status import client_status, offer_kind_of_row
from src.modules.bff.domain.enums import ClientStatus
from src.modules.decision.facade import ClientDecisionDTO
from src.modules.notifications.facade import FeedItemDTO
from src.modules.projector.facade import ApplicationOverviewDTO, TimelineEntryDTO


@dataclass(frozen=True, slots=True)
class ApplicationRowDTO:
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

    @classmethod
    def of(cls, row: ApplicationOverviewDTO) -> Self:
        return cls(
            id=row.application_id,
            number=row.number,
            product_code=row.product_code,
            product_name=row.product_name,
            amount=row.amount,
            term_months=row.term_months,
            status=row.status,
            client_status=client_status(
                row.status, row.client_stage, offer_kind_of_row(row.amount, row.offer_amount)
            ),
            client_stage=row.client_stage,
            action_required=row.action_required,
            offer_amount=row.offer_amount,
            offer_rate=row.offer_rate,
            submitted_at=row.submitted_at,
            updated_at=row.updated_at,
        )


@dataclass(frozen=True, slots=True)
class ApplicationListDTO:
    items: tuple[ApplicationRowDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class OrganizationRefDTO:
    id: UUID
    name: str
    inn: str


@dataclass(frozen=True, slots=True)
class ProductInfoDTO:
    code: str
    name: str | None
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal


@dataclass(frozen=True, slots=True)
class HeadConsentDTO:
    required: bool
    given: bool
    given_at: datetime | None
    head_name: str


@dataclass(frozen=True, slots=True)
class ApplicationConsentsDTO:
    # None — the registry names no head of the company.
    head_credit_bureau: HeadConsentDTO | None


@dataclass(frozen=True, slots=True)
class ClientApplicationCardDTO:
    id: UUID
    number: str
    organization: OrganizationRefDTO | None
    product: ProductInfoDTO
    status: str
    client_status: ClientStatus
    client_stage: str | None
    request: LoanRequestDTO | None
    product_fields: dict[str, Any]
    collateral: CollateralDTO | None
    documents: tuple[DocumentDTO, ...]
    # The open request for information, if the bank is waiting for an answer.
    info_request: InfoRequestDTO | None
    offer: OfferDTO | None
    # The summary kept in the card when the decision module is not reachable.
    decision: ClientDecisionDTO | DecisionSummaryDTO | None
    consents: ApplicationConsentsDTO
    # Client entries only.
    timeline: tuple[TimelineEntryDTO, ...]
    feed: tuple[FeedItemDTO, ...]
    available_actions: tuple[str, ...]
    my_permissions: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    closed_at: datetime | None
    degraded: tuple[str, ...]
