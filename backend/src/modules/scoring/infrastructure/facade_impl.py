from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.enrichment.facade import CreditHistoryDTO
from src.modules.scoring.application.ports import ScoringModel
from src.modules.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    RequestInput,
    ScoringInput,
    TaxInput,
)
from src.modules.scoring.domain.prescreen import FounderPrescreen, PersonHistoryInput
from src.modules.scoring.facade import (
    CompanyProfileDTO,
    EstimateDTO,
    FactorDTO,
    PersonPrescreenDTO,
    PrescreenReasonDTO,
    ScoringResultDTO,
)
from src.modules.scoring.infrastructure.config_loader import default_prescreen
from src.modules.scoring.infrastructure.repository import SqlAlchemyScoringRepository

# Предодобрение оценивает компанию без заявки: номинальные параметры запроса и
# чистая кредитная история по умолчанию (оценка ориентировочная, не решение).
_ESTIMATE_TERM_MONTHS = 12
_ESTIMATE_RATE_BASE = Decimal("21.5")


class ScoringFacadeImpl:
    """Чтение результата для decision/bff, быстрый estimate для предодобрения и предскрин
    учредителя стартапа."""

    def __init__(
        self,
        session: AsyncSession,
        scorecard: ScoringModel,
        prescreen: FounderPrescreen | None = None,
    ) -> None:
        self._repo = SqlAlchemyScoringRepository(session)
        self._scorecard = scorecard
        self._prescreen = prescreen or default_prescreen()

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
        if result is None or result.application_id is None:
            return None
        return ScoringResultDTO(
            id=result.id,
            application_id=result.application_id,
            model_version=result.model_version,
            score=result.score,
            grade=result.grade,
            factors=tuple(
                FactorDTO(
                    code=f.code,
                    value=f.value,
                    bin=f.bin,
                    points=f.points,
                    direction=f.direction,
                    client_hint=f.client_hint,
                )
                for f in result.factors
            ),
            flags=tuple(result.flags),
            data_completeness=result.data_completeness,
            computed_at=result.computed_at,
            segment=result.segment,
            scorecard=result.scorecard,
            pd_12m=result.pd_12m,
            reason_codes=result.reason_codes,
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
            as_of=date.today(),
        )
        output = self._scorecard.calculate(scoring_input)
        return EstimateDTO(
            score=output.score,
            grade=output.grade,
            flags=tuple(output.flags),
            factors=tuple(
                FactorDTO(
                    code=f.code,
                    value=f.value,
                    bin=f.bin,
                    points=f.points,
                    direction=f.direction,
                    client_hint=f.client_hint,
                )
                for f in output.factors
            ),
            segment=output.segment,
            pd_12m=output.pd_12m,
        )
