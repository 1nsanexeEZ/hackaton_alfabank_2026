"""Проектная оценка стартапа: бизнес-план из clients, продукт для стартапа, предскрин,
оценка scoring, предложение STARTUP с basis = project, хранение и срок действия. Соседи —
фейки (кроме одной оценки настоящим scoring), хранилище — настоящее."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed.products import catalog
from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import ValidationError
from src.core.messaging.contracts.decision import PreApprovedOffersUpdated
from src.modules.clients.facade import BusinessPlanDTO, FinancialModelDTO, PlanMonthDTO
from src.modules.decision.application.ports import (
    FounderPrescreen,
    PreApprovedOffer,
    PrescreenCheck,
    ProjectAssessment,
)
from src.modules.decision.application.project_assessment import AssessProjectUseCase
from src.modules.decision.facade import PreApprovedOfferDTO
from src.modules.decision.infrastructure.config_loader import default_policy
from src.modules.decision.infrastructure.facade_impl import DecisionFacadeImpl
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyFounderPrescreenRepository,
    SqlAlchemyPreApprovedOfferRepository,
    SqlAlchemyProjectAssessmentRepository,
)
from src.modules.products.application.borrowers import borrower_profile
from src.modules.products.application.mappers import check_dto, product_dto
from src.modules.scoring.facade import ScoringFacade
from src.modules.scoring.infrastructure.config_loader import load_pd_model
from src.modules.scoring.infrastructure.facade_impl import ScoringFacadeImpl
from tests.fakes import builders
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.messaging import FakeOutboxWriter
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.scoring_facade import PROJECT_FAILED, FakeScoringFacade

NOW = builders.NOW
Sessions = async_sessionmaker[AsyncSession]


def business_plan(organization_id: UUID, **model: Any) -> BusinessPlanDTO:
    values: dict[str, Any] = {
        "months": (PlanMonthDTO(Decimal("1000000"), Decimal("800000")),) * 24,
        "own_funds": Decimal("1000000"),
        "collateral_value": Decimal("0"),
        "collateral_description": None,
        "guarantee": "msp_corporation",
        "guarantee_share": Decimal("0.5"),
        "loan_amount": Decimal("3000000"),
        "loan_term_months": 36,
        **model,
    }
    return BusinessPlanDTO(
        organization_id=organization_id,
        summary="Кофейня у метро",
        financial_model=FinancialModelDTO(**values),
        submitted_by=None,
        submitted_at=NOW - timedelta(hours=1),
        revision=2,
    )


class _World:
    def __init__(self, code: str = "start") -> None:
        self.company = builders.organization_snapshot(code)
        self.clients = FakeClientsFacade()
        self.clients.add_organization(self.company)
        self.clients.business_plans[self.company.id] = business_plan(self.company.id)
        self.products = FakeProductsFacade()
        profile = borrower_profile(self.company)
        for product in catalog():
            self.products.add_product(product_dto(product))
            self.products.set_eligibility(
                check_dto(product.check_eligibility(profile), self.company.id)
            )
        self.scoring: ScoringFacade = FakeScoringFacade()
        self.outbox = FakeOutboxWriter()

    async def prescreen(self, sessions: Sessions, status: str = "passed") -> None:
        async with sessions() as session:
            await SqlAlchemyFounderPrescreenRepository(session).add(
                FounderPrescreen(
                    id=uuid4(),
                    organization_id=self.company.id,
                    founder_account_id=uuid4(),
                    founder_name="Стартов Степан",
                    status=status,  # type: ignore[arg-type]
                    reasons=(PrescreenCheck("no_history", True, "Личных кредитов нет"),),
                    version="prescreen_v1",
                    checked_at=NOW - timedelta(days=1),
                    valid_until=NOW + timedelta(days=29),
                )
            )
            await session.commit()

    async def run(self, sessions: Sessions, clock: FrozenClock | None = None) -> ProjectAssessment:
        async with sessions() as session:
            result = await AssessProjectUseCase(
                SqlAlchemyProjectAssessmentRepository(session),
                SqlAlchemyPreApprovedOfferRepository(session),
                SqlAlchemyFounderPrescreenRepository(session),
                default_policy(),
                self.clients,
                self.products,
                self.scoring,
                clock or FrozenClock(NOW),
            ).run(self.company.id, outbox=self.outbox)
            await session.commit()
        return result

    async def offers(self, sessions: Sessions) -> dict[str, PreApprovedOfferDTO]:
        async with sessions() as session:
            facade = DecisionFacadeImpl(session, FrozenClock(NOW))
            return {o.product_code: o for o in await facade.get_pre_approved(self.company.id)}


async def test_passed_project_is_pre_approved_for_thirty_days(session_factory: Sessions) -> None:
    world = _World()
    await world.prescreen(session_factory)

    result = await world.run(session_factory)

    assert result.status == "passed" and result.product_code == "STARTUP"
    assert result.plan_revision == 2 and result.version == "project_v1"
    # Проект выдерживает 3 818 411,03 — вниз до шага суммы.
    assert result.max_amount == Decimal("3810000.00")
    assert result.valid_until == NOW + timedelta(days=30)
    [asked] = world.scoring.project_calls  # type: ignore[attr-defined]
    # Срок плана в рамках продукта, платёж — по верхней ставке коридора STARTUP.
    assert (asked.amount, asked.term_months, asked.rate) == (Decimal("3000000"), 36, Decimal(26))
    assert asked.okved_main == world.company.okved_main and asked.prescreen_passed
    assert len(asked.monthly_revenue) == 24

    offer = (await world.offers(session_factory))["STARTUP"]
    assert offer.basis == "project" and offer.max_amount == Decimal("3810000.00")
    assert offer.rate_from == Decimal("15") and offer.term_max_months == 60
    assert offer.valid_until == (NOW + timedelta(days=30)).date()
    [staged] = world.outbox.messages
    assert staged.message == PreApprovedOffersUpdated(organization_id=world.company.id)

    async with session_factory() as session:
        dto = await DecisionFacadeImpl(session, FrozenClock(NOW)).get_project_assessment(
            world.company.id
        )
        later = await DecisionFacadeImpl(
            session, FrozenClock(NOW + timedelta(days=31))
        ).get_project_assessment(world.company.id)
    assert dto is not None and dto.status == "passed" and dto.valid
    assert dto.figures.dscr == Decimal("1.65") and dto.figures.capacity == Decimal("3818411.03")
    assert dto.figures.rate == Decimal(26) and dto.figures.requested_amount == Decimal(3000000)
    assert later is not None and not later.valid


async def test_without_a_valid_prescreen_scoring_is_told_so(session_factory: Sessions) -> None:
    world = _World()
    await world.prescreen(session_factory, status="failed")

    await world.run(session_factory)

    [asked] = world.scoring.project_calls  # type: ignore[attr-defined]
    assert not asked.prescreen_passed


async def test_failed_project_withdraws_the_offer(session_factory: Sessions) -> None:
    world = _World()
    await world.prescreen(session_factory)
    await world.run(session_factory)
    world.scoring.project = PROJECT_FAILED  # type: ignore[attr-defined]

    result = await world.run(session_factory, FrozenClock(NOW + timedelta(minutes=5)))

    assert result.status == "failed" and result.max_amount is None
    assert [(r.code, r.passed) for r in result.reasons] == [("dscr", False)]
    assert "STARTUP" not in await world.offers(session_factory)
    async with session_factory() as session:
        latest = await SqlAlchemyProjectAssessmentRepository(session).latest_for_organization(
            world.company.id
        )
    assert latest is not None and latest.status == "failed"


async def test_real_scoring_too_little_for_the_product(session_factory: Sessions) -> None:
    """Настоящий scoring: поток выдерживает меньше минимума STARTUP (500 тыс.) — предложить
    нечего, хотя правила на запрошенной сумме пройдены."""
    world = _World()
    world.scoring = ScoringFacadeImpl(None, load_pd_model())  # type: ignore[arg-type]
    world.clients.business_plans[world.company.id] = business_plan(
        world.company.id,
        months=(PlanMonthDTO(Decimal("100000"), Decimal("85000")),) * 24,
        loan_amount=Decimal("200000"),
        loan_term_months=12,
    )
    await world.prescreen(session_factory)

    result = await world.run(session_factory)

    assert result.status == "failed" and result.max_amount is None
    assert [r.code for r in result.reasons if not r.passed] == ["product_amount"]
    assert result.figures.capacity < Decimal(500000)
    assert await world.offers(session_factory) == {}


async def test_estimate_and_project_offers_live_apart(session_factory: Sessions) -> None:
    world = _World()
    await world.prescreen(session_factory)
    await world.run(session_factory)
    estimate = PreApprovedOffer(
        organization_id=world.company.id,
        product_code="OVERDRAFT",
        max_amount=Decimal("1000000"),
        rate_from=Decimal("20"),
        term_max_months=12,
        basis="estimate",
        factors_summary=(),
        valid_until=(NOW + timedelta(days=30)).date(),
        computed_at=NOW,
    )

    async with session_factory() as session:
        offers = SqlAlchemyPreApprovedOfferRepository(session)
        # Пересчёт по оценке без заявки (новый клиент — пусто) не снимает проектное.
        await offers.replace_for_organization(world.company.id, [])
        await offers.replace_for_organization(world.company.id, [estimate])
        await session.commit()
    assert set(await world.offers(session_factory)) == {"STARTUP", "OVERDRAFT"}

    world.scoring.project = PROJECT_FAILED  # type: ignore[attr-defined]
    await world.run(session_factory)
    assert set(await world.offers(session_factory)) == {"OVERDRAFT"}


async def test_no_business_plan_nothing_is_assessed(session_factory: Sessions) -> None:
    world = _World()
    world.clients.business_plans.clear()

    with pytest.raises(ValidationError) as caught:
        await world.run(session_factory)

    assert caught.value.details == {"code": "business_plan_required"}
    assert world.scoring.project_calls == []  # type: ignore[attr-defined]
    assert world.outbox.messages == []


async def test_a_business_with_turnover_gets_no_startup_loan(session_factory: Sessions) -> None:
    world = _World("romashka")

    with pytest.raises(ValidationError) as caught:
        await world.run(session_factory)

    assert caught.value.details == {"code": "product_not_eligible"}


async def test_the_term_is_kept_within_the_product(session_factory: Sessions) -> None:
    world = _World()
    plan = world.clients.business_plans[world.company.id]
    world.clients.business_plans[world.company.id] = replace(
        plan, financial_model=replace(plan.financial_model, loan_term_months=120)
    )

    result = await world.run(session_factory)

    assert result.figures.term_months == 60


async def test_unknown_company_has_no_assessment(session_factory: Sessions) -> None:
    async with session_factory() as session:
        facade = DecisionFacadeImpl(session, FrozenClock(NOW))
        assert await facade.get_project_assessment(uuid4()) is None

