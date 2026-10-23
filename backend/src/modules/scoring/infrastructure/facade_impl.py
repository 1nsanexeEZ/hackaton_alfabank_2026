from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.clock import Clock, SystemClock
from src.modules.enrichment.facade import CreditHistoryDTO
from src.modules.scoring.application.ports import ScoringModel
from src.modules.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    Factor,
    MlScore,
    RequestInput,
    ScoringInput,
    TaxInput,
)
from src.modules.scoring.domain.prescreen import FounderPrescreen, PersonHistoryInput
from src.modules.scoring.domain.project import ProjectAssessment, ProjectInput
from src.modules.scoring.facade import (
    CompanyProfileDTO,
    EstimateDTO,
    FactorDTO,
    MlScoreDTO,
    PersonPrescreenDTO,
    PrescreenReasonDTO,
    ProjectAssessmentDTO,
    ProjectDTO,
    ProjectReasonDTO,
    ScoringResultDTO,
)
from src.modules.scoring.infrastructure.config_loader import default_prescreen, default_project
from src.modules.scoring.infrastructure.repository import SqlAlchemyScoringRepository

# Предодобрение оценивает компанию без заявки: номинальные параметры запроса и
# чистая кредитная история по умолчанию (оценка ориентировочная, не решение).
_ESTIMATE_TERM_MONTHS = 12
_ESTIMATE_RATE_BASE = Decimal("21.5")


class ScoringFacadeImpl:
    """Чтение результата для decision/bff, быстрый estimate для предодобрения, предскрин
    учредителя стартапа и проектная оценка стартапа."""

    def __init__(
        self,
        session: AsyncSession,
        scorecard: ScoringModel,
        prescreen: FounderPrescreen | None = None,
        clock: Clock | None = None,
        project: ProjectAssessment | None = None,
    ) -> None:
        self._repo = SqlAlchemyScoringRepository(session)
        self._scorecard = scorecard
        self._prescreen = prescreen or default_prescreen()
        self._clock = clock or SystemClock()
        self._project = project or default_project()

    def assess_project(self, project: ProjectDTO) -> ProjectAssessmentDTO:
        output = self._project.assess(
            ProjectInput(
                monthly_revenue=project.monthly_revenue,
                monthly_expenses=project.monthly_expenses,
                own_funds=project.own_funds,
                collateral_value=project.collateral_value,
                guarantee_share=project.guarantee_share,
                amount=project.amount,
                term_months=project.term_months,
                rate=project.rate,
                okved_main=project.okved_main,
                prescreen_passed=project.prescreen_passed,
            )
        )
        metrics = output.metrics
        return ProjectAssessmentDTO(
            version=output.version,
            passed=output.passed,
            reasons=tuple(ProjectReasonDTO(r.code, r.passed, r.message) for r in output.reasons),
            max_amount=output.max_amount,
            cash_flow=metrics.cash_flow,
            debt_service=metrics.debt_service,
            dscr=metrics.dscr,
            own_share=metrics.own_share,
            coverage=metrics.coverage,
        )

    def prescreen_person(self, history: CreditHistoryDTO | None) -> PersonPrescreenDTO:
        output = self._prescreen.check(
            None
            if history is None
            else PersonHistoryInput(
                current_overdue_days=max((o.overdue_days for o in history.obligations), default=0),
                max_overdue_days_12m=history.max_overdue_days_12m,
                inquiries_last_30d=history.inquiries_last_30d,
                monthly_payments=history.total_monthly_payments,
                obligations=len(history.obligations),
            )
        )
        return PersonPrescreenDTO(
            version=output.version,
            passed=output.passed,
            reasons=tuple(PrescreenReasonDTO(r.code, r.passed, r.message) for r in output.reasons),
        )

    async def get_result(self, application_id: UUID) -> ScoringResultDTO | None:
        result = await self._repo.latest_for_application(application_id)
        if result is None:
            return None
        return ScoringResultDTO(
            id=result.id,
            application_id=result.application_id,
            model_version=result.model_version,
            score=result.score,
            grade=result.grade,
            factors=_factors(result.factors),
            flags=tuple(result.flags),
            data_completeness=result.data_completeness,
            computed_at=result.computed_at,
            segment=result.segment,
            scorecard=result.scorecard,
            pd_12m=result.pd_12m,
            reason_codes=result.reason_codes,
            ml=_ml(result.ml) if result.ml is not None else None,
            quality=result.quality,
            quality_reasons=result.quality_reasons,
        )

    def estimate(self, company: CompanyProfileDTO, amount: Decimal | None = None) -> EstimateDTO:
        scoring_input = ScoringInput(
            request=RequestInput(
                amount=amount or Decimal(0),
                term_months=_ESTIMATE_TERM_MONTHS,
                product_code="UNSECURED",
                facility="term_loan",
                rate_base=_ESTIMATE_RATE_BASE,
            ),
            company=CompanyInput(
                legal_form=company.legal_form,
                business_age_months=company.business_age_months,
                okved_main=company.okved_main,
                verification_status=company.verification_status,
                registry_status=company.registry_status,
                declared_revenue=company.annual_revenue,
                declared_revenue_previous=company.previous_annual_revenue,
                monthly_debt_payments_declared=None,
            ),
            tax=TaxInput(tax_arrears=None, reported_revenue=None),
            bureau=BureauInput(
                available=True,
                has_history=True,
                max_overdue_days_12m=0,
                inquiries_last_30d=0,
                total_monthly_payments=Decimal(0),
            ),
            collateral=CollateralInput(declared_value=None),
            cashflow=CashflowInput(
                present=False,
                gap_detected=None,
                gap_month=None,
                gap_amount=None,
                revenue_confirmed=None,
            ),
            mass_address=False,
            sources_failed=(),
            as_of=self._clock.now().date(),
        )
        output = self._scorecard.calculate(scoring_input)
        return EstimateDTO(
            score=output.score,
            grade=output.grade,
            flags=tuple(output.flags),
            factors=_factors(output.factors),
            segment=output.segment,
            pd_12m=output.pd_12m,
        )


def _factors(factors: tuple[Factor, ...]) -> tuple[FactorDTO, ...]:
    return tuple(
        FactorDTO(
            code=f.code,
            value=f.value,
            bin=f.bin,
            points=f.points,
            direction=f.direction,
            client_hint=f.client_hint,
        )
        for f in factors
    )


def _ml(ml: MlScore) -> MlScoreDTO:
    return MlScoreDTO(
        model_version=ml.model_version,
        pd_12m=ml.pd_12m,
        score=ml.score,
        grade=ml.grade,
        factors=_factors(ml.factors),
        reason_codes=ml.reason_codes,
    )
