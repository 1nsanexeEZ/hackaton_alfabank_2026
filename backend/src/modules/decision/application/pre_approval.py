"""Use case RecalculatePreApproved: «вам доступно до …» на главной кабинета.

По событиям clients (отчётность подана, компания проверена) и в демо-сиде:
1. компания — снимок clients, оценка — `scoring.estimate` без БКИ и выписок (консервативно);
2. для каждого активного продукта: не проходит eligibility — пропускаем; дальше политика
   (`CreditPolicy.pre_approve`): стоп-факторы, лимит на грейд осторожнее, ставка от;
3. предложения действуют 30 дней; пересчёт перезаписывает все предложения компании —
   продукт, который больше не подходит, пропадает.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.messaging.contracts.decision import PreApprovedOffersUpdated
from src.core.messaging.outbox import OutboxWriter
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.decision.application.input_builder import latest_annual_report
from src.modules.decision.application.ports import PreApprovedOffer, PreApprovedOfferRepository
from src.modules.decision.domain.model import PreApprovalInput, ProductInput, SupportProgramInput
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.products.facade import ProductDTO, ProductsFacade
from src.modules.scoring.facade import CompanyProfileDTO, ScoringFacade

PRE_APPROVAL_VALID_DAYS = 30


class RecalculatePreApprovedUseCase:
    def __init__(
        self,
        repository: PreApprovedOfferRepository,
        policy: CreditPolicy,
        clients: ClientsFacade,
        products: ProductsFacade,
        scoring: ScoringFacade,
        clock: Clock,
        key_rate: Decimal,
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clients = clients
        self._products = products
        self._scoring = scoring
        self._clock = clock
        self._key_rate = key_rate

    async def on_event(
        self, organization_id: UUID, *, event_id: UUID, outbox: OutboxWriter
    ) -> list[PreApprovedOffer]:
        offers = await self.recalculate(organization_id)
        await outbox.add(
            PreApprovedOffersUpdated(organization_id=organization_id),
            key=organization_id,
            correlation_id=organization_id,
            causation_id=event_id,
        )
        return offers

    async def recalculate(self, organization_id: UUID) -> list[PreApprovedOffer]:
        company = await self._clients.get_snapshot(organization_id)
        estimate = self._scoring.estimate(_company_profile(company))
        report = latest_annual_report(company)
        now = self._clock.now()
        valid_until = (now + timedelta(days=PRE_APPROVAL_VALID_DAYS)).date()

        offers: list[PreApprovedOffer] = []
        for product in await self._products.list_active():
            check = await self._products.check_eligibility(product.code, organization_id)
            if not check.eligible:
                continue
            approval = self._policy.pre_approve(
                PreApprovalInput(
                    product=product_input(product),
                    grade=estimate.grade,
                    score=estimate.score,
                    registry_status=company.registry_status,
                    annual_revenue=report.revenue if report is not None else None,
                    okved_main=company.okved_main,
                ),
                key_rate=self._key_rate,
            )
            if approval is None:
                continue
            offers.append(
                PreApprovedOffer(
                    organization_id=organization_id,
                    product_code=approval.product_code,
                    max_amount=approval.max_amount,
                    rate_from=approval.rate_from,
                    term_max_months=approval.term_max_months,
                    basis="estimate",
                    factors_summary=approval.factors_summary,
                    valid_until=valid_until,
                    computed_at=now,
                )
            )
        await self._repository.replace_for_organization(organization_id, offers)
        return offers


def product_input(product: ProductDTO) -> ProductInput:
    """Рамки продукта из каталога (у предодобрения заявки ещё нет)."""
    program = product.support_program
    return ProductInput(
        code=product.code,
        amount_min=product.amount_min,
        amount_max=product.amount_max,
        term_min_months=product.term_min_months,
        term_max_months=product.term_max_months,
        rate_base=product.rate_base,
        rate_max=product.rate_max,
        repayment_options=tuple(product.repayment_options),
        collateral_required=product.collateral_kind == "required",
        auto_decision_limit=product.auto_decision_limit,
        support_program=SupportProgramInput(
            code=program.code,
            rate_cap=program.rate_cap,
            msp_registry_required=program.msp_registry_required,
            okved_whitelist=frozenset(program.okved_whitelist),
        )
        if program is not None
        else None,
        guarantee=product.guarantee,
        target_use_confirmation=product.target_use_confirmation,
    )


def _company_profile(company: OrganizationSnapshotDTO) -> CompanyProfileDTO:
    annual = sorted(
        (r for r in company.financial_reports if r.period_quarter is None),
        key=lambda r: r.period_year,
        reverse=True,
    )
    return CompanyProfileDTO(
        legal_form=company.legal_form,
        business_age_months=company.business_age_months,
        okved_main=company.okved_main,
        annual_revenue=annual[0].revenue if annual else None,
        previous_annual_revenue=annual[1].revenue if len(annual) > 1 else None,
        verification_status=company.verification_status,
        registry_status=company.registry_status,
    )
