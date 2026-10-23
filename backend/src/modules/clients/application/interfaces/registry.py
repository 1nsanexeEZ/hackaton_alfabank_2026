from typing import Protocol
from uuid import UUID

from src.modules.clients.domain.value_objects import RegistryExtract


class RegistryLookup(Protocol):
    """ЕГРЮЛ/ЕГРИП extracts in our value objects. InfrastructureError — the
    registry did not answer or answered with something we cannot read."""

    async def lookup(self, inn: str) -> RegistryExtract | None:
        """By INN, asked past any cache. None — the registry does not know the INN."""
        ...

    async def of_application(self, application_id: UUID) -> tuple[UUID, RegistryExtract] | None:
        """The extract enrichment already fetched for an application, with the
        company it was fetched for. None — no snapshot or no extract in it
        (the source failed)."""
        ...
