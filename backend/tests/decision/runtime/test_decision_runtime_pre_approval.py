"""Предодобрение по событиям clients и ночным пакетом: сверка с ЕГРЮЛ, eligibility, оценка
скоринга, политика, хранение."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed.products import catalog
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.decision import PreApprovedOffersUpdated
from src.core.messaging.outbox import OutboxRecord
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.decision.application.policy_versions import ActivePolicyProvider
from src.modules.decision.application.ports import PreApprovedOffer
from src.modules.decision.application.pre_approval import RecalculatePreApprovedUseCase
from src.modules.decision.application.refresh_pre_approved import (
    RefreshExpiringPreApprovedUseCase,
)
from src.modules.decision.facade import PreApprovedOfferDTO
from src.modules.decision.infrastructure.config_loader import (
    CreditPolicyDocuments,
    default_policy,
)
from src.modules.decision.infrastructure.facade_impl import DecisionFacadeImpl
from src.modules.decision.infrastructure.models import PreApprovedOfferRecord
from src.modules.decision.infrastructure.repository import SqlAlchemyPreApprovedOfferRepository
from src.modules.decision.infrastructure.transaction import SqlAlchemyPreApprovalTransaction
from src.modules.market.facade import MarketFacade
from src.modules.products.application.borrowers import borrower_profile
from src.modules.products.application.mappers import check_dto, product_dto
from src.modules.products.facade import EligibilityCheckDTO, EligibilityReasonDTO, ProductsFacade
from src.modules.scoring.facade import EstimateDTO, ScoringFacade
from tests.fakes import builders
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.market_facade import FakeMarketFacade
from tests.fakes.messaging import FakeOutboxWriter
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.scoring_facade import FakeScoringFacade

NOW = builders.NOW
KEY_RATE = Decimal("16.50")
Sessions = async_sessionmaker[AsyncSession]


def _estimate(
    grade: str = "A", pd: str = "0.0041", score: int = 800, segment: str = "legal_entity"
) -> EstimateDTO:
    """Оценка PD-модели (pd_model_v2): грейд A–J и PD."""
    return EstimateDTO(
        score=score,
        grade=grade,  # type: ignore[arg-type]
        flags=(),
        factors=(),
        segment=segment,  # type: ignore[arg-type]
        pd_12m=Decimal(pd),
    )


class _World:
    def __init__(self, code: str, estimate: EstimateDTO | None = None) -> None:
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
        self.scoring = FakeScoringFacade(estimate or _estimate())

    def not_eligible(self, code: str) -> None:
        self.products.set_eligibility(
            EligibilityCheckDTO(
                code,
                self.company.id,
                eligible=False,
                reasons=(EligibilityReasonDTO("revenue", False, "Мало выручки"),),
            )
        )

    def verification(self, status: str) -> None:
        self.company = replace(self.company, verification_status=status)  # type: ignore[arg-type]
        self.clients.add_organization(self.company)

    def eligible_codes(self) -> set[str]:
        return {
            code
            for (code, _), check in self.products.eligibility.items()
            if check.eligible and self.products.products[code].status == "active"
        }

    async def recalculate(self, sessions: Sessions, at: datetime = NOW) -> FakeOutboxWriter:
        outbox = FakeOutboxWriter()
        async with sessions() as session:
            use_case = RecalculatePreApprovedUseCase(
                SqlAlchemyPreApprovedOfferRepository(session),
                default_policy(),
                self.clients,
                self.products,
                self.scoring,
                FrozenClock(at),
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

    async def valid_until(self, sessions: Sessions) -> set[date]:
        """Сроки всех хранимых предложений, и истекших тоже."""
        async with sessions() as session:
            repository = SqlAlchemyPreApprovedOfferRepository(session)
            return {o.valid_until for o in await repository.list_for_organization(self.company.id)}

    def joins(self, other: _World) -> None:
        """Соседи `other` отвечают и за эту компанию: ночной пакет видит обе через одни фасады."""
        self.clients.add_organization(other.company)
        self.products.eligibility.update(other.products.eligibility)


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
    # Ромашка: грейд A → лимит на ступень осторожнее (B, k = 0,45) от выручки; ставка из
    # компонент (17,5 + 0,18 + 2 + 3,5) ниже базы продукта — база.
    revenue = world.company.financial_reports[0].revenue
    assert unsecured.max_amount == min(Decimal(30_000_000), Decimal("0.45") * revenue)
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
    world.scoring.default_estimate = _estimate("C", "0.0153", score=705)
    await world.recalculate(session_factory)

    offers = await world.offers(session_factory)
    assert "CREDIT_LINE" not in offers
    # Грейд C → лимит по D (k = 0,3; автоматика по D–E — до 15 млн), ставка с EL по PD C.
    revenue = world.company.financial_reports[0].revenue
    assert offers["UNSECURED"].max_amount == Decimal("0.3") * revenue
    assert offers["UNSECURED"].rate_from == Decimal("23.69")


async def test_stop_factors_leave_no_offers(session_factory: Sessions) -> None:
    liquidating = _World("zakat", _estimate("B", "0.0059"))
    worst = _World("romashka", _estimate("J", "0.5161", score=400))

    await liquidating.recalculate(session_factory)
    await worst.recalculate(session_factory)

    assert await liquidating.offers(session_factory) == {}
    assert await worst.offers(session_factory) == {}


async def test_new_client_gets_no_pre_approval(session_factory: Sessions) -> None:
    """Оборотов в банке меньше полугода — только полный скоринг по заявке."""
    world = _World("ivanov", _estimate("C", "0.0153", segment="new_client"))

    outbox = await world.recalculate(session_factory)

    assert await world.offers(session_factory) == {}
    [staged] = outbox.messages
    assert staged.message == PreApprovedOffersUpdated(organization_id=world.company.id)


async def test_unverified_company_gets_no_offers(session_factory: Sessions) -> None:
    """Сверки с ЕГРЮЛ не было — предскоринга нет; событие уходит, как при любом пересчёте."""
    world = _World("romashka")
    world.verification("unverified")

    outbox = await world.recalculate(session_factory)

    assert await world.offers(session_factory) == {}
    [staged] = outbox.messages
    assert staged.message == PreApprovedOffersUpdated(organization_id=world.company.id)


async def test_registry_mismatch_removes_offers(session_factory: Sessions) -> None:
    """OrganizationVerificationMismatch: прежние предложения компании снимаются."""
    world = _World("romashka")
    await world.recalculate(session_factory)
    assert await world.offers(session_factory)

    world.verification("mismatch")
    outbox = await world.recalculate(session_factory)

    assert await world.offers(session_factory) == {}
    [staged] = outbox.messages
    assert staged.message == PreApprovedOffersUpdated(organization_id=world.company.id)

    world.verification("verified")
    await world.recalculate(session_factory)
    assert await world.offers(session_factory)


async def test_expired_offers_are_not_shown(session_factory: Sessions) -> None:
    world = _World("romashka")
    await world.recalculate(session_factory)

    later = FrozenClock(NOW + timedelta(days=31))

    assert await world.offers(session_factory, later) == {}
    assert await world.offers(session_factory, FrozenClock(NOW + timedelta(days=30)))


# --- ночной пакет ---------------------------------------------------------------


def _refresh(
    sessions: Sessions, world: _World, key_rate: Decimal = KEY_RATE
) -> RefreshExpiringPreApprovedUseCase:
    """Ночной пакет на настоящих транзакциях; соседи — фейки `world`, политика — активная в БД
    (версий нет — встроенная)."""
    facades = FacadeRegistry()
    facades.register(ClientsFacade, lambda _session: world.clients)
    facades.register(ProductsFacade, lambda _session: world.products)
    facades.register(ScoringFacade, lambda _session: world.scoring)
    facades.register(MarketFacade, lambda _session: FakeMarketFacade(key_rate))
    clock = FrozenClock(NOW)
    transactions = partial(SqlAlchemyPreApprovalTransaction, sessions, facades, clock)
    policies = ActivePolicyProvider(CreditPolicyDocuments())
    return RefreshExpiringPreApprovedUseCase(transactions, policies, clock)


async def _published(sessions: Sessions) -> list[dict[str, Any]]:
    async with sessions() as session:
        stmt = (
            select(OutboxRecord.envelope)
            .where(OutboxRecord.message_type == PreApprovedOffersUpdated.TYPE)
            .order_by(OutboxRecord.id)
        )
        return list(await session.scalars(stmt))


async def test_nightly_refresh_renews_expiring_offers(session_factory: Sessions) -> None:
    """Истекают через 2 дня и уже истекли — пересчёт на 30 дней; через 20 дней — не трогаем."""
    expiring = _World("romashka")
    expired = _World("progress")
    fresh = _World("sboy")
    expiring.joins(expired)
    expiring.joins(fresh)
    await expiring.recalculate(session_factory, NOW - timedelta(days=28))
    await expired.recalculate(session_factory, NOW - timedelta(days=40))
    await fresh.recalculate(session_factory, NOW - timedelta(days=10))
    renewed = (NOW + timedelta(days=30)).date()
    assert await expiring.valid_until(session_factory) == {(NOW + timedelta(days=2)).date()}

    refreshed = await _refresh(session_factory, expiring).execute(within_days=3)

    assert refreshed == 2
    assert await expiring.valid_until(session_factory) == {renewed}
    assert await expired.valid_until(session_factory) == {renewed}
    assert await fresh.valid_until(session_factory) == {(NOW + timedelta(days=20)).date()}
    published = await _published(session_factory)
    assert {e["payload"]["organization_id"] for e in published} == {
        str(expiring.company.id),
        str(expired.company.id),
    }
    assert all(e["producer"] == "decision" and e["causation_id"] is None for e in published)

    # Следующей ночью продлевать нечего.
    assert await _refresh(session_factory, expiring).execute(within_days=3) == 0


async def test_nightly_refresh_checks_the_registry(session_factory: Sessions) -> None:
    """Пакет идёт тем же пересчётом: компания разошлась с ЕГРЮЛ — предложения сняты."""
    world = _World("romashka")
    await world.recalculate(session_factory, NOW - timedelta(days=28))
    world.verification("mismatch")

    assert await _refresh(session_factory, world).execute(within_days=3) == 1

    assert await world.valid_until(session_factory) == set()


async def test_nightly_refresh_failure_does_not_stop_others(session_factory: Sessions) -> None:
    """Компания пропала из clients — её предложения остаются как были, остальные продлены."""
    lost = _World("progress")
    world = _World("romashka")
    await lost.recalculate(session_factory, NOW - timedelta(days=29))
    await world.recalculate(session_factory, NOW - timedelta(days=28))
    before = await lost.valid_until(session_factory)

    assert await _refresh(session_factory, world).execute(within_days=3) == 1

    assert await lost.valid_until(session_factory) == before
    assert await world.valid_until(session_factory) == {(NOW + timedelta(days=30)).date()}
    assert [e["payload"]["organization_id"] for e in await _published(session_factory)] == [
        str(world.company.id)
    ]


# --- смена ключевой ставки -----------------------------------------------------------


async def _key_rates(sessions: Sessions, world: _World) -> set[Decimal | None]:
    async with sessions() as session:
        stmt = select(PreApprovedOfferRecord.key_rate).where(
            PreApprovedOfferRecord.organization_id == world.company.id
        )
        return {None if v is None else Decimal(str(v)) for v in await session.scalars(stmt)}


async def test_new_key_rate_reprices_offers(session_factory: Sessions) -> None:
    """Предложения свежие, но посчитаны по 16,50: ключевая 14 — пересчёт сразу, без истечения."""
    world = _World("romashka")
    other = _World("progress")
    world.joins(other)
    await world.recalculate(session_factory)
    await other.recalculate(session_factory)
    assert await _key_rates(session_factory, world) == {KEY_RATE}

    new_rate = Decimal("14.00")
    assert await _refresh(session_factory, world, new_rate).execute(within_days=3) == 2

    assert await _key_rates(session_factory, world) == {new_rate}
    assert await _key_rates(session_factory, other) == {new_rate}
    published = await _published(session_factory)
    assert {e["payload"]["organization_id"] for e in published} == {
        str(world.company.id),
        str(other.company.id),
    }
    # Ставка та же — пересчитывать нечего.
    assert await _refresh(session_factory, world, new_rate).execute(within_days=3) == 0


def _stored(organization: Any, basis: str, key_rate: str | None, at: datetime) -> PreApprovedOffer:
    return PreApprovedOffer(
        organization_id=organization,
        product_code="UNSECURED",
        max_amount=Decimal("1000000"),
        rate_from=Decimal("21"),
        term_max_months=36,
        basis=basis,  # type: ignore[arg-type]
        factors_summary=(),
        valid_until=(at + timedelta(days=30)).date(),
        computed_at=at,
        key_rate=None if key_rate is None else Decimal(key_rate),
    )


async def test_companies_priced_at_another_key_rate(session_factory: Sessions) -> None:
    """Старая ставка и незаписанная — устаревшие, раньше посчитанные первыми; проектные — нет."""
    old, unknown, project, current = uuid4(), uuid4(), uuid4(), uuid4()
    async with session_factory() as session:
        offers = SqlAlchemyPreApprovedOfferRepository(session)
        await offers.replace_for_organization(old, [_stored(old, "estimate", "16.50", NOW)])
        await offers.replace_for_organization(
            unknown, [_stored(unknown, "estimate", None, NOW - timedelta(days=1))]
        )
        await offers.replace_project_offers(project, [_stored(project, "project", None, NOW)])
        await offers.replace_for_organization(current, [_stored(current, "estimate", "14", NOW)])
        await session.commit()

        assert await offers.organizations_priced_at_other_key_rate(Decimal("14"), 10) == [
            unknown,
            old,
        ]
        assert await offers.organizations_priced_at_other_key_rate(Decimal("14"), 1) == [unknown]
