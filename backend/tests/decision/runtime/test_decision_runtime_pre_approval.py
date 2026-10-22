"""Предодобрение по событиям clients: eligibility, оценка скоринга, политика, хранение."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed.products import catalog
from src.clients.facade import OrganizationSnapshotDTO
from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.decision import PreApprovedOffersUpdated
from src.decision.application.pre_approval import RecalculatePreApprovedUseCase
from src.decision.facade import PreApprovedOfferDTO
from src.decision.infrastructure.config_loader import default_policy
from src.decision.infrastructure.facade_impl import DecisionFacadeImpl
from src.decision.infrastructure.repository import SqlAlchemyPreApprovedOfferRepository
from src.products.application.borrowers import borrower_profile
from src.products.application.mappers import check_dto, product_dto
from src.products.facade import EligibilityCheckDTO, EligibilityReasonDTO
from src.scoring.facade import EstimateDTO
from tests.fakes import builders
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.messaging import FakeOutboxWriter
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.scoring_facade import FakeScoringFacade

NOW = builders.NOW
KEY_RATE = Decimal("16.50")
Sessions = async_sessionmaker[AsyncSession]


class _World:
    def __init__(self, code: str, grade: str = "A", score: int = 790) -> None:
        self.company: OrganizationSnapshotDTO = builders.organization_snapshot(code)
        self.clients = FakeClientsFacade()
        self.clients.add_organization(self.company)
        self.products = FakeProductsFacade()
        profile = borrower_profile(self.company)
        for product in catalog():
            self.products.add_product(product_dto(product))
            self.products.set_eligibility(
                check_dto(product.check_eligibility(profile), self.company.id)
            )
        self.scoring = FakeScoringFacade(
            EstimateDTO(score=score, grade=grade, flags=(), factors=())  # type: ignore[arg-type]
        )

    def not_eligible(self, code: str) -> None:
        self.products.set_eligibility(
            EligibilityCheckDTO(
                code,
                self.company.id,
                eligible=False,
                reasons=(EligibilityReasonDTO("revenue", False, "Мало выручки"),),
            )
        )

    def eligible_codes(self) -> set[str]:
        return {
            code
            for (code, _), check in self.products.eligibility.items()
            if check.eligible and self.products.products[code].status == "active"
        }

    async def recalculate(self, sessions: Sessions) -> FakeOutboxWriter:
        outbox = FakeOutboxWriter()
        async with sessions() as session:
            use_case = RecalculatePreApprovedUseCase(
                SqlAlchemyPreApprovedOfferRepository(session),
                default_policy(),
                self.clients,
                self.products,
                self.scoring,
                FrozenClock(NOW),
                KEY_RATE,
            )
            await use_case.on_event(self.company.id, event_id=EVENT, outbox=outbox)
            await session.commit()
        return outbox

    async def offers(
        self, sessions: Sessions, clock: FrozenClock | None = None
    ) -> dict[str, PreApprovedOfferDTO]:
        async with sessions() as session:
            facade = DecisionFacadeImpl(session, clock or FrozenClock(NOW))
            return {o.product_code: o for o in await facade.get_pre_approved(self.company.id)}


EVENT = uuid4()


async def test_offers_for_eligible_products(session_factory: Sessions) -> None:
    world = _World("romashka")

    outbox = await world.recalculate(session_factory)

    [staged] = outbox.messages
    assert staged.message == PreApprovedOffersUpdated(organization_id=world.company.id)
    assert staged.causation_id == EVENT and staged.key == str(world.company.id)
    offers = await world.offers(session_factory)
    assert offers and set(offers) <= world.eligible_codes()
    unsecured = offers["UNSECURED"]
    # Ромашка: грейд A → лимит на ступень осторожнее (B, k = 0,4) от выручки, ставка — база.
    revenue = world.company.financial_reports[0].revenue
    assert unsecured.max_amount == min(Decimal(30_000_000), Decimal("0.4") * revenue)
    assert unsecured.rate_from == Decimal("23.50")
    assert unsecured.term_max_months == 60
    assert unsecured.valid_until == (NOW + timedelta(days=30)).date()
    assert unsecured.basis == "estimate"


async def test_not_eligible_product_is_skipped(session_factory: Sessions) -> None:
    world = _World("romashka")
    world.not_eligible("UNSECURED")

    await world.recalculate(session_factory)

    offers = await world.offers(session_factory)
    assert "UNSECURED" not in offers
    assert offers


async def test_recalculation_replaces_offers(session_factory: Sessions) -> None:
    world = _World("romashka")
    await world.recalculate(session_factory)
    assert "CREDIT_LINE" in await world.offers(session_factory)

    world.not_eligible("CREDIT_LINE")
    world.scoring.default_estimate = EstimateDTO(score=620, grade="C", flags=(), factors=())
    await world.recalculate(session_factory)

    offers = await world.offers(session_factory)
    assert "CREDIT_LINE" not in offers
    # Грейд C → лимит по D (k = 0,15), ставка с надбавкой за C.
    revenue = world.company.financial_reports[0].revenue
    assert offers["UNSECURED"].max_amount == Decimal("0.15") * revenue
    assert offers["UNSECURED"].rate_from == Decimal("27.00")


async def test_stop_factors_leave_no_offers(session_factory: Sessions) -> None:
    liquidating = _World("zakat", grade="B", score=700)
    worst = _World("romashka", grade="E", score=395)

    await liquidating.recalculate(session_factory)
    await worst.recalculate(session_factory)

    assert await liquidating.offers(session_factory) == {}
    assert await worst.offers(session_factory) == {}


async def test_expired_offers_are_not_shown(session_factory: Sessions) -> None:
    world = _World("romashka")
    await world.recalculate(session_factory)

    later = FrozenClock(NOW + timedelta(days=31))

    assert await world.offers(session_factory, later) == {}
    assert await world.offers(session_factory, FrozenClock(NOW + timedelta(days=30)))
