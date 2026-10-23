"""Reads of other modules through their facades, for texts, recipients and the
news profile.

The feed is a by-product: a module that is not wired yet or an entity that is
gone degrades the text ("Заявка отправлена" without a number) instead of
failing the event and sending it to the dead letter queue. So every read
returns None or an empty list instead of raising."""

from typing import Protocol
from uuid import UUID

from src.modules.applications.facade import ApplicationCardDTO
from src.modules.clients.facade import OrganizationSnapshotDTO
from src.modules.decision.facade import DecisionDTO, PreApprovedOfferDTO
from src.modules.scoring.facade import ScoringResultDTO


class FacadeLookup(Protocol):
    """Facades of other modules bound to the current transaction (`ctx.facade`).
    An unregistered facade raises a LookupError (FacadeNotRegisteredError)."""

    def __call__[T](self, key: type[T]) -> T: ...


class Neighbours(Protocol):
    async def card(self, application_id: UUID) -> ApplicationCardDTO | None: ...

    async def organization(self, organization_id: UUID) -> OrganizationSnapshotDTO | None: ...

    async def members(self, organization_id: UUID) -> list[UUID]: ...

    async def product_name(self, code: str) -> str | None: ...

    async def scoring(self, application_id: UUID) -> ScoringResultDTO | None: ...

    async def decision(self, application_id: UUID) -> DecisionDTO | None: ...

    async def pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]: ...

    async def application_products(self, organization_id: UUID) -> list[str]:
        """Product codes of the company's applications."""
        ...

    async def account_role(self, account_id: UUID) -> str | None: ...
