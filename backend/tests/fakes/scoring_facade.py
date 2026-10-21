from decimal import Decimal
from uuid import UUID

from src.scoring.facade import CompanyProfileDTO, EstimateDTO, ScoringResultDTO


class FakeScoringFacade:
    def __init__(self, estimate: EstimateDTO | None = None) -> None:
        self.results: dict[UUID, ScoringResultDTO] = {}
        self.default_estimate = estimate or EstimateDTO(score=700, grade="B", flags=(), factors=())
        self.estimate_calls: list[CompanyProfileDTO] = []

    def add_result(self, result: ScoringResultDTO) -> ScoringResultDTO:
        self.results[result.application_id] = result
        return result

    async def get_result(self, application_id: UUID) -> ScoringResultDTO | None:
        return self.results.get(application_id)

    def estimate(self, company: CompanyProfileDTO, amount: Decimal | None = None) -> EstimateDTO:
        self.estimate_calls.append(company)
        return self.default_estimate
