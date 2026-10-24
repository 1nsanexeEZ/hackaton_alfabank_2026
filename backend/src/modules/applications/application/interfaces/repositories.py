from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.value_objects import ApplicationNumber, DecidedBy


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
        decided_by: DecidedBy | None = None,
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
