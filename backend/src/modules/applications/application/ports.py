"""What the use cases need from the outside world."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.value_objects import ApplicationNumber


class ApplicationRepository(Protocol):
    async def next_number(self, year: int) -> ApplicationNumber: ...

    async def add(self, application: CreditApplication) -> None: ...

    async def get(
        self, application_id: UUID, access: AccessContext | None = None
    ) -> CreditApplication:
        """NotFoundError when missing or hidden by the caller's policies."""
        ...

    async def save(self, application: CreditApplication) -> None: ...

    async def find_active(
        self, organization_id: UUID, product_code: str, exclude_id: UUID | None = None
    ) -> UUID | None: ...

    async def search(
        self,
        access: AccessContext | None,
        organization_id: UUID | None,
        statuses: Sequence[str] | None,
        limit: int,
        offset: int,
    ) -> list[CreditApplication]: ...

    async def offers_expired_by(self, moment: datetime, limit: int) -> list[UUID]: ...

    async def set_client_stage(
        self, application_id: UUID, client_stage: str, now: datetime
    ) -> bool:
        """Update the stage label of a not closed application without touching
        its version; False — closed, unknown or already this label."""
        ...

    async def record_signature_details(
        self,
        application_id: UUID,
        ip: str | None,
        user_agent: str | None,
        edo_document_id: str | None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StoredObject:
    size: int
    content_type: str


class DocumentStorage(Protocol):
    """Private bucket; the browser talks to it only through short-lived URLs."""

    async def presign_upload(
        self, key: str, content_type: str, size: int, ttl_seconds: int
    ) -> PresignedUpload: ...

    async def presign_download(self, key: str, filename: str, ttl_seconds: int) -> str: ...

    async def head(self, key: str) -> StoredObject | None: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class EdoReceipt:
    document_id: str
    # True while signing goes through the mock of the electronic document flow.
    simulated: bool


class EdoClient(Protocol):
    # True while the document flow is a mock: the contract says so to the client.
    simulated: bool

    async def sign(
        self, application_id: UUID, number: str, offer_hash: str, signer_id: UUID
    ) -> EdoReceipt: ...


@dataclass(frozen=True, slots=True)
class DisbursementReceipt:
    reference: str
    # True while payout goes through the mock of the core banking system.
    simulated: bool


class AbsClient(Protocol):
    """Core banking system (АБС): opens the loan account and pays the credit out."""

    async def disburse(
        self,
        application_id: UUID,
        number: str,
        organization_id: UUID,
        amount: Decimal,
        term_months: int,
        rate: Decimal,
    ) -> DisbursementReceipt: ...
