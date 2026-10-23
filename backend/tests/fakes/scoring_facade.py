from decimal import Decimal
from uuid import UUID

from src.modules.enrichment.facade import CreditHistoryDTO
from src.modules.scoring.facade import (
    CompanyProfileDTO,
    EstimateDTO,
    PersonPrescreenDTO,
    PrescreenReasonDTO,
    ScoringResultDTO,
)

PRESCREEN_PASSED = PersonPrescreenDTO(
    "prescreen_v1",
    True,
    (PrescreenReasonDTO("no_current_overdue", True, "Текущей просрочки по личным кредитам нет"),),
)
PRESCREEN_FAILED = PersonPrescreenDTO(
    "prescreen_v1",
    False,
    (PrescreenReasonDTO("no_current_overdue", False, "Есть текущая просрочка по личным кредитам"),),
)


class FakeScoringFacade:
    def __init__(self, estimate: EstimateDTO | None = None) -> None:
        self.results: dict[UUID, ScoringResultDTO] = {}
        self.default_estimate = estimate or EstimateDTO(score=700, grade="B", flags=(), factors=())
        self.estimate_calls: list[CompanyProfileDTO] = []
        self.prescreen = PRESCREEN_PASSED
        self.prescreen_calls: list[CreditHistoryDTO | None] = []

    def add_result(self, result: ScoringResultDTO) -> ScoringResultDTO:
        self.results[result.application_id] = result
        return result

    async def get_result(self, application_id: UUID) -> ScoringResultDTO | None:
        return self.results.get(application_id)

    def estimate(self, company: CompanyProfileDTO, amount: Decimal | None = None) -> EstimateDTO:
        self.estimate_calls.append(company)
        return self.default_estimate

    def prescreen_person(self, history: CreditHistoryDTO | None) -> PersonPrescreenDTO:
        self.prescreen_calls.append(history)
        return self.prescreen
