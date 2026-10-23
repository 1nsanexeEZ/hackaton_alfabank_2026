"""Предскрин учредителя стартапа: учредитель по реестру, его согласие, БКИ физлица, оценка
scoring, хранение и срок действия. Соседи — фейки, хранилище — настоящее."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import InfrastructureError, ValidationError
from src.modules.decision.application.founder_prescreen import FounderPrescreenUseCase
from src.modules.decision.application.ports import FounderPrescreen
from src.modules.decision.infrastructure.facade_impl import DecisionFacadeImpl
from src.modules.decision.infrastructure.repository import SqlAlchemyFounderPrescreenRepository
from src.modules.enrichment.facade import CreditHistoryDTO
from tests.fakes import builders
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.enrichment_facade import FakeEnrichmentFacade
from tests.fakes.identity_facade import FakeIdentityFacade
from tests.fakes.scoring_facade import PRESCREEN_FAILED, FakeScoringFacade

NOW = builders.NOW
Sessions = async_sessionmaker[AsyncSession]
HISTORY = CreditHistoryDTO((), 1, False, 0, Decimal(0))


class _World:
    def __init__(self) -> None:
        self.company = builders.organization_snapshot("start")
        self.clients = FakeClientsFacade()
        self.clients.add_organization(self.company)
        self.identity = FakeIdentityFacade()
        founder = self.identity.add_account(last_name="Стартов", first_name="Степан")
        self.founder = founder.id
        self.clients.add_member(self.founder, self.company.id, "director")
        self.clients.registry_heads[self.company.id] = self.founder
        self.identity.give_consent(self.founder, "credit_bureau_personal", NOW - timedelta(hours=1))
        self.enrichment = FakeEnrichmentFacade()
        self.enrichment.add_person_history("Стартов", self.company.inn, HISTORY)
        self.scoring = FakeScoringFacade()

    async def run(self, sessions: Sessions) -> FounderPrescreen:
        async with sessions() as session:
            result = await FounderPrescreenUseCase(
                SqlAlchemyFounderPrescreenRepository(session),
                self.clients,
                self.identity,
                self.enrichment,
                self.scoring,
                FrozenClock(NOW),
            ).run(self.company.id)
            await session.commit()
        return result


async def test_passed_prescreen_is_stored_for_thirty_days(session_factory: Sessions) -> None:
    world = _World()

    result = await world.run(session_factory)

    assert result.status == "passed" and result.founder_account_id == world.founder
    assert result.founder_name == "Стартов Степан"
    assert result.valid_until == NOW + timedelta(days=30)
    [(person, consent_at)] = world.enrichment.person_requests
    assert (person.last_name, person.company_inn) == ("Стартов", world.company.inn)
    assert consent_at == NOW - timedelta(hours=1)
    assert world.scoring.prescreen_calls == [HISTORY]

    async with session_factory() as session:
        dto = await DecisionFacadeImpl(session, FrozenClock(NOW)).get_founder_prescreen(
            world.company.id
        )
        later = await DecisionFacadeImpl(
            session, FrozenClock(NOW + timedelta(days=31))
        ).get_founder_prescreen(world.company.id)
    assert dto is not None and dto.status == "passed" and dto.valid
    assert later is not None and not later.valid


async def test_failed_prescreen_keeps_the_reasons(session_factory: Sessions) -> None:
    world = _World()
    world.scoring.prescreen = PRESCREEN_FAILED

    result = await world.run(session_factory)

    assert result.status == "failed"
    assert [(r.code, r.passed) for r in result.reasons] == [("no_current_overdue", False)]


async def test_the_latest_prescreen_wins(session_factory: Sessions) -> None:
    world = _World()
    world.scoring.prescreen = PRESCREEN_FAILED
    await world.run(session_factory)
    world.scoring = FakeScoringFacade()
    async with session_factory() as session:
        await FounderPrescreenUseCase(
            SqlAlchemyFounderPrescreenRepository(session),
            world.clients,
            world.identity,
            world.enrichment,
            world.scoring,
            FrozenClock(NOW + timedelta(minutes=5)),
        ).run(world.company.id)
        await session.commit()

    async with session_factory() as session:
        latest = await SqlAlchemyFounderPrescreenRepository(session).latest_for_organization(
            world.company.id
        )
    assert latest is not None and latest.status == "passed"


async def test_without_the_consent_nothing_is_asked(session_factory: Sessions) -> None:
    world = _World()
    world.identity.consents.clear()

    with pytest.raises(ValidationError) as caught:
        await world.run(session_factory)

    assert caught.value.details == {"code": "consent_required", "consent": "credit_bureau_personal"}
    assert world.enrichment.person_requests == []


async def test_no_founder_by_the_registry(session_factory: Sessions) -> None:
    world = _World()
    world.clients.registry_heads.clear()

    with pytest.raises(ValidationError) as caught:
        await world.run(session_factory)

    assert caught.value.details == {"code": "founder_not_found"}


async def test_bureau_down_is_503_and_stores_nothing(session_factory: Sessions) -> None:
    world = _World()
    world.enrichment.person_bureau_down = True

    with pytest.raises(InfrastructureError):
        await world.run(session_factory)

    async with session_factory() as session:
        repository = SqlAlchemyFounderPrescreenRepository(session)
        assert await repository.latest_for_organization(world.company.id) is None


async def test_unknown_company_has_no_prescreen(session_factory: Sessions) -> None:
    async with session_factory() as session:
        facade = DecisionFacadeImpl(session, FrozenClock(NOW))
        assert await facade.get_founder_prescreen(uuid4()) is None
