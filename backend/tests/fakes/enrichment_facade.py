from datetime import datetime
from uuid import UUID

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.facade import (
    CreditHistoryDTO,
    EnrichmentSnapshotDTO,
    PersonDTO,
    RegistryExtractDTO,
)


class FakeEnrichmentFacade:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, EnrichmentSnapshotDTO] = {}
        self.registry: dict[str, RegistryExtractDTO] = {}
        # (last name, company INN) -> the person's credit history.
        self.people: dict[tuple[str, str], CreditHistoryDTO] = {}
        self.person_bureau_down = False
        self.person_requests: list[tuple[PersonDTO, datetime]] = []

    def add_snapshot(self, snapshot: EnrichmentSnapshotDTO) -> EnrichmentSnapshotDTO:
        self.snapshots[snapshot.application_id] = snapshot
        return snapshot

    def add_registry_extract(self, extract: RegistryExtractDTO) -> RegistryExtractDTO:
        self.registry[extract.inn] = extract
        return extract

    def add_person_history(
        self, last_name: str, company_inn: str, history: CreditHistoryDTO
    ) -> CreditHistoryDTO:
        self.people[(last_name, company_inn)] = history
        return history

    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None:
        return self.snapshots.get(application_id)

    async def lookup_registry(self, inn: str, *, fresh: bool = False) -> RegistryExtractDTO | None:
        return self.registry.get(inn)

    async def lookup_person_bureau(
        self, person: PersonDTO, consent_at: datetime
    ) -> CreditHistoryDTO | None:
        self.person_requests.append((person, consent_at))
        if self.person_bureau_down:
            raise InfrastructureError("Бюро кредитных историй временно недоступно")
        return self.people.get((person.last_name, person.company_inn))
