"""Domain events of the application. The application layer maps them to
`applications.events` contracts before they go to the outbox."""

from dataclasses import dataclass
from uuid import UUID

from src.core.domain import DomainEvent, Money


@dataclass(frozen=True, kw_only=True)
class ApplicationEvent(DomainEvent):
    application_id: UUID
    organization_id: UUID


@dataclass(frozen=True, kw_only=True)
class ApplicationSubmitted(ApplicationEvent):
    product_code: str
    amount: Money
    term_months: int
    purpose: str


@dataclass(frozen=True, kw_only=True)
class ApplicationStatusChanged(ApplicationEvent):
    from_status: str
    to_status: str
    client_stage: str | None = None


@dataclass(frozen=True, kw_only=True)
class ApplicationInfoProvided(ApplicationEvent):
    info_request_id: UUID
    document_ids: tuple[UUID, ...]


@dataclass(frozen=True, kw_only=True)
class OfferAccepted(ApplicationEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class OfferDeclined(ApplicationEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class OfferExpired(ApplicationEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class ApplicationSigned(ApplicationEvent):
    signed_by: UUID


@dataclass(frozen=True, kw_only=True)
class ApplicationCancelled(ApplicationEvent):
    reason: str | None = None
