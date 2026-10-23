"""Сборка доменного `DecisionInput` из того, что отдают соседи:

- заявка, снимок компании и копия условий продукта — `applications.get_scoring_input`,
  дозапросы — `applications.get_card`;
- ЕГРЮЛ, ФНС, БКИ компании и руководителя, ГИР БО, Контур и прогноз по выписке —
  `enrichment.get_snapshot`;
- грейд, флаги и подсказки — `scoring.get_result`;
- программа господдержки, поручительство и альтернативы — `products`.

Здесь граница: DTO соседей переводятся во вход политики, домен про фасады не знает.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade, ScoringInputDTO
from src.modules.clients.facade import FinancialReportDTO, OrganizationSnapshotDTO
from src.modules.decision.application.ports import FounderPrescreenRepository
from src.modules.decision.domain.model import (
    AccountingInput,
    AlternativeInput,
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    CounterpartyInput,
    DecisionInput,
    FounderPrescreenStatus,
    Grade,
    HeadBureauInput,
    ProductInput,
    RequestInput,
    ScoreInput,
    SupportProgramInput,
    on_scale,
)
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.domain.result import DecisionInputRefs
from src.modules.enrichment.facade import EnrichmentFacade, EnrichmentSnapshotDTO
from src.modules.products.facade import ProductDTO, ProductsFacade
from src.modules.scoring.facade import ScoringFacade, ScoringResultDTO

# Внешние источники: сбой любого — данных для стоп-факторов не хватает, решает андеррайтер.
_EXTERNAL_SOURCES = ("egrul", "fns", "bki", "gir_bo", "kontur", "bki_head")


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
        prescreens: FounderPrescreenRepository | None = None,
    ) -> None:
        self._policy = policy
        self._applications = applications
        self._enrichment = enrichment
        self._scoring = scoring
        self._products = products
        self._prescreens = prescreens

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
            company=_company_input(source.organization, snapshot, source.submitted_at.date()),
            score=_score_input(result, self._policy.config.grade_scale),
            bureau=_bureau_input(source.organization, snapshot),
            cashflow=_cashflow_input(snapshot),
            collateral=CollateralInput(source.collateral.type, source.collateral.declared_value)
            if source.collateral is not None
            else None,
            sources_failed=_sources_failed(snapshot),
            revenue_info_requested=self._revenue_requested(card),
            alternatives=alternatives,
            counterparty=_counterparty_input(snapshot),
            accounting=_accounting_input(snapshot),
            head_bureau=_head_bureau_input(snapshot),
            founder_prescreen=await self._founder_prescreen(source),
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

    async def _founder_prescreen(self, source: ScoringInputDTO) -> FounderPrescreenStatus | None:
        """Только у продукта для стартапа: последний предскрин и действовал ли он при подаче."""
        if source.product_code not in self._policy.config.startup_products:
            return None
        if self._prescreens is None:
            return "missing"
        prescreen = await self._prescreens.latest_for_organization(source.organization_id)
        if prescreen is None:
            return "missing"
        if not prescreen.valid_at(source.submitted_at):
            return "expired"
        return prescreen.status

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
    organization: OrganizationSnapshotDTO, snapshot: EnrichmentSnapshotDTO | None, as_of: date
) -> CompanyInput:
    egrul = snapshot.egrul if snapshot is not None else None
    fns = snapshot.fns if snapshot is not None else None
    report = latest_annual_report(organization)
    head_since = egrul.head_since if egrul is not None else None
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
        tax_arrears=fns.tax_arrears if fns is not None else None,
        account_blocks=len(fns.account_blocks) if fns is not None else None,
        head_tenure_months=_full_months(head_since, as_of) if head_since is not None else None,
        head_since_registration=(
            egrul is not None and head_since is not None and head_since <= egrul.registered_at
        ),
    )


def _full_months(since: date, until: date) -> int:
    months = (until.year - since.year) * 12 + until.month - since.month
    return max(months - (1 if until.day < since.day else 0), 0)


def _score_input(result: ScoringResultDTO | None, scale: tuple[Grade, ...]) -> ScoreInput | None:
    """Грейд — на шкалу политики: результат scorecard_v1 (A–E, без PD) и PD-модели (A–J)."""
    if result is None:
        return None
    return ScoreInput(
        score=result.score,
        grade=on_scale(result.grade, from_pd_model=result.pd_12m is not None, scale=scale),
        flags=frozenset(result.flags),
        client_hints=tuple(f.client_hint for f in result.factors if f.client_hint),
        pd_12m=result.pd_12m,
        ml_grade=result.ml.grade if result.ml is not None else None,
        ml_pd_12m=result.ml.pd_12m if result.ml is not None else None,
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
        current_overdue_days=current,
        debt_balance=sum((o.balance for o in bki.obligations), Decimal(0)),
    )


def _counterparty_input(snapshot: EnrichmentSnapshotDTO | None) -> CounterpartyInput | None:
    kontur = snapshot.kontur if snapshot is not None else None
    if kontur is None:
        return None
    return CounterpartyInput(
        bankruptcy_messages=len(kontur.bankruptcy_messages),
        enforcement_sum=kontur.enforcement.sum,
        lawsuits_sum=kontur.arbitration.defendant_sum,
    )


def _accounting_input(snapshot: EnrichmentSnapshotDTO | None) -> AccountingInput | None:
    gir_bo = snapshot.gir_bo if snapshot is not None else None
    latest = gir_bo.latest if gir_bo is not None and gir_bo.available else None
    if latest is None:
        return None
    return AccountingInput(year=latest.year, revenue=latest.revenue, equity=latest.equity)


def _head_bureau_input(snapshot: EnrichmentSnapshotDTO | None) -> HeadBureauInput:
    """БКИ руководителя: ответ, или почему его нет (не дал согласия, руководитель не найден,
    бюро не ответило, источник не запрашивали)."""
    if snapshot is None:
        return HeadBureauInput("not_requested")
    if snapshot.bki_head is not None:
        current = max((o.overdue_days for o in snapshot.bki_head.obligations), default=0)
        return HeadBureauInput("ok", current)
    skipped = {e.source: e.code for e in snapshot.sources_skipped}
    code = skipped.get("bki_head")
    if code in ("no_consent", "no_head"):
        return HeadBureauInput(code)  # type: ignore[arg-type]
    if any(e.source == "bki_head" for e in snapshot.sources_failed):
        return HeadBureauInput("failed")
    return HeadBureauInput("not_requested")


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
        monthly_inflows=tuple(month.inflow for month in cashflow.months_history),
        annual_inflow=cashflow.annual_inflow,
    )


def _sources_failed(snapshot: EnrichmentSnapshotDTO | None) -> tuple[str, ...]:
    if snapshot is None:
        return _EXTERNAL_SOURCES
    return tuple(
        dict.fromkeys(e.source for e in snapshot.sources_failed if e.source in _EXTERNAL_SOURCES)
    )
