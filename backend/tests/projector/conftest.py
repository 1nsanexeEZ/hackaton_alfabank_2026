from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.modules.projector.infrastructure.adapters.projector_facade import ProjectorFacadeImpl
from src.modules.projector.infrastructure.repositories.read_model_store import (
    SqlAlchemyReadModelStore,
)
from src.modules.projector.presentation.dependencies import projector_facade
from tests.projector.world import Consumer, OpenFacade, OpenStore, World


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def consumer(session_factory: async_sessionmaker[AsyncSession], world: World) -> Consumer:
    return Consumer(session_factory, world.registry)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def facade(session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock) -> OpenFacade:
    """`async with facade() as projector:` — the facade on a fresh session."""

    @asynccontextmanager
    async def open_facade() -> AsyncGenerator[ProjectorFacadeImpl]:
        async with session_factory() as session:
            yield projector_facade(session, clock)

    return open_facade


@pytest.fixture
def store(session_factory: async_sessionmaker[AsyncSession]) -> OpenStore:
    """`async with store() as s:` — writes are committed on exit."""

    @asynccontextmanager
    async def open_store() -> AsyncGenerator[SqlAlchemyReadModelStore]:
        async with session_factory() as session:
            yield SqlAlchemyReadModelStore(session)
            await session.commit()

    return open_store
