"""Back office screens carry the facade DTOs as they are: the bank sees everything."""

from pydantic import BaseModel, ConfigDict

from src.modules.applications.facade import ApplicationCardDTO
from src.modules.bff.application.dto.backoffice import StartupProjectDTO
from src.modules.bff.domain.enums import ClientStatus
from src.modules.decision.facade import DecisionDTO
from src.modules.enrichment.facade import EnrichmentSnapshotDTO
from src.modules.process.facade import ProcessViewDTO, UserTaskDTO
from src.modules.products.facade import EligibilityCheckDTO
from src.modules.projector.facade import TimelineEntryDTO
from src.modules.scoring.facade import ScoringResultDTO


class UnderwriterCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    application: ApplicationCardDTO
    client_status: ClientStatus
    # Registry, tax, credit bureau, cash flow forecast for the gap chart.
    enrichment: EnrichmentSnapshotDTO | None
    scoring: ScoringResultDTO | None
    # With rule_trace, reason codes and limits: why the decision is what it is.
    decision: DecisionDTO | None
    # Why the product fits the company (or does not).
    product_fit: EligibilityCheckDTO | None
    timeline: list[TimelineEntryDTO]
    # Current node and the path passed, to highlight the diagram.
    process: ProcessViewDTO | None
    # The open underwriter task with its form.
    task: UserTaskDTO | None
    degraded: list[str]
    # A startup: the project assessment before the application, the business plan, and the
    # project assessment form filled in from them (`form`) — the underwriter confirms it.
    startup: StartupProjectDTO | None = None
