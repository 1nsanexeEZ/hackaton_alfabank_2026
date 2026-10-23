"""Use case AssessProject: «проектная оценка → вам предодобрен кредит» ветки стартапа.

На общей схеме у стартапа: предскрин учредителя → бизнес-план и финмодель → проектная оценка →
«вам предодобрен кредит» → общий путь заявки. Клиент заполняет бизнес-план в кабинете
(clients) и запускает оценку:
1. бизнес-план — из clients; нет — 422 `business_plan_required`;
2. продукт — для стартапа (`startup_only`, из `startup.products` политики) и подходит компании
   по eligibility; нет — 422 `product_not_eligible`;
3. предскрин учредителя — последний, пройден и действует на сейчас; нет — правило scoring не
   пройдено, клиент видит причину;
4. оценка — `scoring.assess_project` по финмодели: запрошенная сумма, срок плана в рамках
   продукта, платёж — по верхней ставке коридора продукта: предодобренная сумма выдерживает
   любую ставку, которую назначит андеррайтер;
5. прошла → предложение по продукту с `basis = project` на 30 дней: сумма — сколько
   выдерживает проект, не больше максимума продукта, вниз до шага суммы; меньше минимума
   продукта — предложить нечего, оценка не пройдена. Не прошла — проектное предложение
   снимается. Предложения по оценке без заявки (`estimate`) оценка не трогает;
6. оценка хранится и действует 30 дней, как предодобрение; в ленту клиента —
   `PreApprovedOffersUpdated` («вам предодобрен кредит»).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ValidationError
from src.core.messaging.contracts.decision import PreApprovedOffersUpdated
from src.core.messaging.outbox import OutboxWriter
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.application.ports import (
    FounderPrescreenRepository,
    PreApprovedOffer,
    PreApprovedOfferRepository,
    ProjectAssessment,
    ProjectAssessmentRepository,
    ProjectCheck,
    ProjectFigures,
)
from src.modules.decision.domain.policy import CreditPolicy, round_down
from src.modules.products.facade import ProductDTO, ProductsFacade
from src.modules.scoring.facade import ProjectDTO, ScoringFacade

PROJECT_VALID_DAYS = 30


class AssessProjectUseCase:
    def __init__(
        self,
        repository: ProjectAssessmentRepository,
        offers: PreApprovedOfferRepository,
        prescreens: FounderPrescreenRepository,
        policy: CreditPolicy,
        clients: ClientsFacade,
        products: ProductsFacade,
        scoring: ScoringFacade,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._offers = offers
        self._prescreens = prescreens
        self._policy = policy
        self._clients = clients
        self._products = products
        self._scoring = scoring
        self._clock = clock

    async def run(self, organization_id: UUID, *, outbox: OutboxWriter) -> ProjectAssessment:
        plan = await self._clients.get_business_plan(organization_id)
        if plan is None:
            raise ValidationError(
                "Сначала заполните бизнес-план и финансовую модель",
                details={"code": "business_plan_required"},
            )
        product = await self._startup_product(organization_id)
        company = await self._clients.get_snapshot(organization_id)
        now = self._clock.now()
        prescreen = await self._prescreens.latest_for_organization(organization_id)
        model = plan.financial_model
        term = min(max(model.loan_term_months, product.term_min_months), product.term_max_months)
        rate = product.rate_max
        checked = self._scoring.assess_project(
            ProjectDTO(
                monthly_revenue=tuple(m.revenue for m in model.months),
                monthly_expenses=tuple(m.expenses for m in model.months),
                own_funds=model.own_funds,
                collateral_value=model.collateral_value,
                guarantee_share=model.guarantee_share,
                amount=model.loan_amount,
                term_months=term,
                rate=rate,
                okved_main=company.okved_main,
                prescreen_passed=prescreen is not None
                and prescreen.status == "passed"
                and prescreen.valid_at(now),
            )
        )
        reasons = tuple(ProjectCheck(r.code, r.passed, r.message) for r in checked.reasons)
        max_amount = None
        if checked.passed:
            amount = round_down(
                min(checked.max_amount, product.amount_max), self._policy.config.amount_step
            )
            if amount >= product.amount_min:
                max_amount = amount
            else:
                reasons += (
                    ProjectCheck(
                        "product_amount",
                        False,
                        "Проект выдерживает меньше минимальной суммы кредита на запуск",
                    ),
                )
        valid_until = now + timedelta(days=PROJECT_VALID_DAYS)
        assessment = ProjectAssessment(
            id=uuid4(),
            organization_id=organization_id,
            product_code=product.code,
            plan_revision=plan.revision,
            status="passed" if max_amount is not None else "failed",
            reasons=reasons,
            figures=ProjectFigures(
                requested_amount=model.loan_amount,
                term_months=term,
                rate=rate,
                cash_flow=checked.cash_flow,
                debt_service=checked.debt_service,
                dscr=checked.dscr,
                own_share=checked.own_share,
                coverage=checked.coverage,
                capacity=checked.max_amount,
            ),
            max_amount=max_amount,
            version=checked.version,
            checked_at=now,
            valid_until=valid_until,
        )
        await self._repository.add(assessment)
        offers = (
            [
                PreApprovedOffer(
                    organization_id=organization_id,
                    product_code=product.code,
                    max_amount=max_amount,
                    rate_from=product.rate_base,
                    term_max_months=product.term_max_months,
                    basis="project",
                    factors_summary=tuple(r.message for r in reasons),
                    valid_until=valid_until.date(),
                    computed_at=now,
                )
            ]
            if max_amount is not None
            else []
        )
        await self._offers.replace_project_offers(organization_id, offers)
        await outbox.add(
            PreApprovedOffersUpdated(organization_id=organization_id),
            key=organization_id,
            correlation_id=organization_id,
        )
        return assessment

    async def _startup_product(self, organization_id: UUID) -> ProductDTO:
        """Продукт для стартапа из политики, который подходит компании."""
        startup = self._policy.config.startup_products
        for product in await self._products.list_active():
            if not product.startup_only or product.code not in startup:
                continue
            check = await self._products.check_eligibility(product.code, organization_id)
            if check.eligible:
                return product
        raise ValidationError(
            "Кредит на запуск бизнеса компании не подходит",
            details={"code": "product_not_eligible"},
        )
