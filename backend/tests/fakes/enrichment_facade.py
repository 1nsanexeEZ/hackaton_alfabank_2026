from uuid import UUID

from src.enrichment.facade import EnrichmentSnapshotDTO, RegistryExtractDTO


class FakeEnrichmentFacade:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, EnrichmentSnapshotDTO] = {}
        self.registry: dict[str, RegistryExtractDTO] = {}

    def add_snapshot(self, snapshot: EnrichmentSnapshotDTO) -> EnrichmentSnapshotDTO:
        self.snapshots[snapshot.application_id] = snapshot
        return snapshot

    def add_registry_extract(self, extract: RegistryExtractDTO) -> RegistryExtractDTO:
        self.registry[extract.inn] = extract
        return extract

    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None:
        return self.snapshots.get(application_id)

    async def lookup_registry(self, inn: str) -> RegistryExtractDTO | None:
        return self.registry.get(inn)
