"""The underwriter card: the bank sees everything, so the blocks are the facade
DTOs as they are."""

from dataclasses import dataclass

from src.modules.applications.facade import ApplicationCardDTO
from src.modules.bff.domain.enums import ClientStatus
from src.modules.decision.facade import DecisionDTO
from src.modules.enrichment.facade import EnrichmentSnapshotDTO
from src.modules.process.facade import ProcessViewDTO, UserTaskDTO
from src.modules.products.facade import EligibilityCheckDTO
from src.modules.projector.facade import TimelineEntryDTO
from src.modules.scoring.facade import ScoringResultDTO


@dataclass(frozen=True, slots=True)
class UnderwriterCardDTO:
    application: ApplicationCardDTO
    client_status: ClientStatus
    enrichment: EnrichmentSnapshotDTO | None
    scoring: ScoringResultDTO | None
    decision: DecisionDTO | None
    product_fit: EligibilityCheckDTO | None
    timeline: tuple[TimelineEntryDTO, ...]
    process: ProcessViewDTO | None
    task: UserTaskDTO | None
    degraded: tuple[str, ...]
