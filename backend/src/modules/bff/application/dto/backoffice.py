"""The underwriter card: the bank sees everything, so the blocks are the facade
DTOs as they are."""

from dataclasses import dataclass

from src.modules.applications.facade import ApplicationCardDTO
from src.modules.bff.domain.enums import ClientStatus
from src.modules.bff.domain.project_form import ProjectForm
from src.modules.clients.facade import BusinessPlanDTO
from src.modules.decision.facade import DecisionDTO, ProjectAssessmentDTO
from src.modules.enrichment.facade import EnrichmentSnapshotDTO
from src.modules.process.facade import ProcessViewDTO, UserTaskDTO
from src.modules.products.facade import EligibilityCheckDTO
from src.modules.projector.facade import TimelineEntryDTO
from src.modules.scoring.facade import ScoringResultDTO


@dataclass(frozen=True, slots=True)
class StartupProjectDTO:
    """A startup's application: the bank's project assessment before it, the business plan it
    was made on and what the project assessment form starts with."""

    assessment: ProjectAssessmentDTO
    business_plan: BusinessPlanDTO | None
    # The plan was revised after the assessment: the figures may be outdated.
    plan_changed: bool
    # The assessment passed and was valid when the application was submitted.
    valid_at_submission: bool
    form: ProjectForm


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
    # Only for a startup's application with a project assessment of its product.
    startup: StartupProjectDTO | None = None
