"""Сборка доменного `DecisionInput` из того, что отдают соседи:

- заявка, снимок компании и копия условий продукта — `applications.get_scoring_input`,
  дозапросы — `applications.get_card`;
- ЕГРЮЛ, ФНС, БКИ и прогноз по выписке — `enrichment.get_snapshot`;
- грейд, флаги и подсказки — `scoring.get_result`;
- программа господдержки, поручительство и альтернативы — `products`.

Здесь граница: DTO соседей переводятся во вход политики, домен про фасады не знает.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from src.applications.facade import ApplicationCardDTO, ApplicationsFacade, ScoringInputDTO
from src.clients.facade import FinancialReportDTO, OrganizationSnapshotDTO
from src.core.exceptions.exceptions import NotFoundError
from src.decision.domain.model import (
    AlternativeInput,
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    DecisionInput,
    ProductInput,
    RequestInput,
    ScoreInput,
    SupportProgramInput,
)
from src.decision.domain.policy import CreditPolicy
from src.decision.domain.result import DecisionInputRefs
from src.enrichment.facade import EnrichmentFacade, EnrichmentSnapshotDTO
from src.products.facade import ProductDTO, ProductsFacade
from src.scoring.facade import ScoringFacade, ScoringResultDTO

# Внешние источники: сбой любого — данных для стоп-факторов не хватает, решает андеррайтер.
_EXTERNAL_SOURCES = ("egrul", "fns", "bki")


@dataclass(frozen=True, slots=True)
class CollectedInput:
    decision_input: DecisionInput
    refs: DecisionInputRefs
    source: ScoringInputDTO


class DecisionInputBuilder:
    def __init__(
        self,
        policy: CreditPolicy,
        applications: ApplicationsFacade,
        enrichment: EnrichmentFacade,
        scoring: ScoringFacade,
        products: ProductsFacade,
    ) -> None:
        self._policy = policy
        self._applications = applications
        self._enrichment = enrichment
        self._scoring = scoring
        self._products = products

    async def collect(self, application_id: UUID) -> CollectedInput:
        source = await self._applications.get_scoring_input(application_id)
        card = await self._applications.get_card(application_id)
        snapshot = await self._enrichment.get_snapshot(application_id)
        result = await self._scoring.get_result(application_id)
        product = await self._product(source.product_code)
        alternatives = await self._alternatives(source)

        decision_input = DecisionInput(
            product=_product_input(source, product),
            request=RequestInput(
                amount=source.request.amount, term_months=source.request.term_months
            ),
            company=_company_input(source.organization, snapshot),
            score=_score_input(result),
            bureau=_bureau_input(source.organization, snapshot),
            cashflow=_cashflow_input(snapshot),
            collateral=CollateralInput(source.collateral.type, source.collateral.declared_value)
            if source.collateral is not None
            else None,
            sources_failed=_sources_failed(snapshot),
            revenue_info_requested=self._revenue_requested(card),
            alternatives=alternatives,
        )
        refs = DecisionInputRefs(
            scoring_result_id=result.id if result is not None else None,
            enrichment_snapshot_id=snapshot.id if snapshot is not None else None,
            product_code=source.product_terms.code,
            product_version=source.product_terms.version,
        )
        return CollectedInput(decision_input, refs, source)

    async def _product(self, code: str) -> ProductDTO | None:
        try:
            return await self._products.get_product(code)
        except NotFoundError:
            return None

    async def _alternatives(self, source: ScoringInputDTO) -> tuple[AlternativeInput, ...]:
        found: list[AlternativeInput] = []
        for code in self._policy.alternative_candidates(source.product_code):
            product = await self._product(code)
            if product is None or product.status != "active":
                continue
            check = await self._products.check_eligibility(code, source.organization_id)
            found.append(AlternativeInput(code, check.eligible, product.amount_min))
        return tuple(found)

    def _revenue_requested(self, card: ApplicationCardDTO) -> bool:
        """Был закрытый дозапрос с выпиской — повторно выручку не запрашиваем."""
        document = self._policy.config.revenue_document
        return any(
            request.status != "open" and document in request.requested_documents
            for request in card.info_requests
        )


def latest_annual_report(organization: OrganizationSnapshotDTO) -> FinancialReportDTO | None:
    annual = [r for r in organization.financial_reports if r.period_quarter is None]
    return max(annual, key=lambda r: r.period_year) if annual else None


def _product_input(source: ScoringInputDTO, product: ProductDTO | None) -> ProductInput:
    terms = source.product_terms
    program = product.support_program if product is not None else None
    return ProductInput(
        code=terms.code,
        amount_min=terms.amount_min,
        amount_max=terms.amount_max,
        term_min_months=terms.term_min_months,
        term_max_months=terms.term_max_months,
        rate_base=terms.rate_base,
        rate_max=terms.rate_max,
        repayment_options=tuple(terms.repayment_options),
        collateral_required=terms.collateral_required,
        auto_decision_limit=terms.auto_decision_limit,
        support_program=SupportProgramInput(
            code=program.code,
            rate_cap=program.rate_cap,
            msp_registry_required=program.msp_registry_required,
            okved_whitelist=frozenset(program.okved_whitelist),
        )
        if program is not None
        else None,
        guarantee=product.guarantee if product is not None else "none",
        target_use_confirmation=product.target_use_confirmation if product is not None else False,
    )


def _company_input(
    organization: OrganizationSnapshotDTO, snapshot: EnrichmentSnapshotDTO | None
) -> CompanyInput:
    egrul = snapshot.egrul if snapshot is not None else None
    fns = snapshot.fns if snapshot is not None else None
    report = latest_annual_report(organization)
    return CompanyInput(
        legal_form=organization.legal_form,
        okved_main=organization.okved_main,
        registry_status=egrul.status if egrul is not None else organization.registry_status,
        verification_status=organization.verification_status,
        declared_revenue=report.revenue if report is not None else None,
        declared_expenses=report.expenses if report is not None else None,
        reported_revenue=fns.reported_revenue if fns is not None else None,
        disqualified_head=fns.disqualified_head if fns is not None else None,
        in_msp_registry=fns.in_msp_registry if fns is not None else None,
        mass_address=egrul.mass_address if egrul is not None else False,
    )


def _score_input(result: ScoringResultDTO | None) -> ScoreInput | None:
    if result is None:
        return None
    return ScoreInput(
        score=result.score,
        grade=result.grade,
        flags=frozenset(result.flags),
        client_hints=tuple(f.client_hint for f in result.factors if f.client_hint),
    )


def _bureau_input(
    organization: OrganizationSnapshotDTO, snapshot: EnrichmentSnapshotDTO | None
) -> BureauInput:
    bki = snapshot.bki if snapshot is not None else None
    if bki is None:
        # Бюро не ответило: платежи по кредитам — со слов клиента из отчёта, если указаны.
        report = latest_annual_report(organization)
        declared = report.monthly_debt_payments if report is not None else None
        return BureauInput(False, None, declared or Decimal(0))
    current = max((o.overdue_days for o in bki.obligations), default=0)
    return BureauInput(
        available=True,
        max_overdue_days=max(current, bki.max_overdue_days_12m),
        monthly_payments=bki.total_monthly_payments,
    )


def _cashflow_input(snapshot: EnrichmentSnapshotDTO | None) -> CashflowInput | None:
    cashflow = snapshot.cashflow if snapshot is not None else None
    if cashflow is None:
        return None
    nets = [month.net for month in cashflow.months_history]
    average = sum(nets, Decimal(0)) / len(nets) if nets else Decimal(0)
    return CashflowInput(
        average_monthly_net=average.quantize(Decimal("0.01")),
        gap_detected=cashflow.gap_detected,
        gap_month=cashflow.gap_month,
        revenue_confirmed=cashflow.revenue_confirmed,
    )


def _sources_failed(snapshot: EnrichmentSnapshotDTO | None) -> tuple[str, ...]:
    if snapshot is None:
        return _EXTERNAL_SOURCES
    return tuple(
        dict.fromkeys(e.source for e in snapshot.sources_failed if e.source in _EXTERNAL_SOURCES)
    )
