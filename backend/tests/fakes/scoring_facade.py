from decimal import Decimal
from uuid import UUID

from src.modules.enrichment.facade import CreditHistoryDTO
from src.modules.scoring.facade import (
    CompanyProfileDTO,
    EstimateDTO,
    PersonPrescreenDTO,
    PrescreenReasonDTO,
    ProjectAssessmentDTO,
    ProjectDTO,
    ProjectReasonDTO,
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

PROJECT_PASSED = ProjectAssessmentDTO(
    version="project_v1",
    passed=True,
    reasons=(
        ProjectReasonDTO("founder_prescreen", True, "Проверка учредителя пройдена"),
        ProjectReasonDTO(
            "dscr", True, "Денежного потока по финмодели хватает на платежи по кредиту с запасом"
        ),
    ),
    max_amount=Decimal("3818411.03"),
    cash_flow=Decimal("4800000.00"),
    debt_service=Decimal("2900924.64"),
    dscr=Decimal("1.65"),
    own_share=Decimal("0.2500"),
    coverage=Decimal("0.5000"),
)
PROJECT_FAILED = ProjectAssessmentDTO(
    version="project_v1",
    passed=False,
    reasons=(
        ProjectReasonDTO(
            "dscr",
            False,
            "Денежного потока по финмодели не хватает на платежи по кредиту с запасом",
        ),
    ),
    max_amount=Decimal("1200000.00"),
    cash_flow=Decimal("1500000.00"),
    debt_service=Decimal("2900924.64"),
    dscr=Decimal("0.51"),
    own_share=Decimal("0.2500"),
    coverage=Decimal("0.5000"),
)


class FakeScoringFacade:
    def __init__(self, estimate: EstimateDTO | None = None) -> None:
        self.results: dict[UUID, ScoringResultDTO] = {}
        # Как отвечает PD-модель для Ромашки: грейд B, PD 0,55%, юрлицо с оборотами.
        self.default_estimate = estimate or EstimateDTO(
            score=700,
            grade="B",
            flags=(),
            factors=(),
            segment="legal_entity",
            pd_12m=Decimal("0.0055"),
        )
        self.estimate_calls: list[CompanyProfileDTO] = []
        self.prescreen = PRESCREEN_PASSED
        self.prescreen_calls: list[CreditHistoryDTO | None] = []
        self.project = PROJECT_PASSED
        self.project_calls: list[ProjectDTO] = []

    def add_result(self, result: ScoringResultDTO) -> ScoringResultDTO:
        self.results[result.application_id] = result
        return result

    async def get_result(self, application_id: UUID) -> ScoringResultDTO | None:
        return self.results.get(application_id)

    async def estimate(
        self, company: CompanyProfileDTO, amount: Decimal | None = None
    ) -> EstimateDTO:
        self.estimate_calls.append(company)
        return self.default_estimate

    def prescreen_person(self, history: CreditHistoryDTO | None) -> PersonPrescreenDTO:
        self.prescreen_calls.append(history)
        return self.prescreen

    def assess_project(self, project: ProjectDTO) -> ProjectAssessmentDTO:
        self.project_calls.append(project)
        return self.project
