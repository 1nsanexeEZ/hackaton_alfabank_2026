"""The rebuild's transaction: a session of its own, committed or rolled back as a whole."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.products.facade import ProductsFacade
from src.modules.projector.infrastructure.adapters.projection_transaction import (
    SqlAlchemyProjectionTransaction,
)
from tests.projector.unit.factories import overview
from tests.projector.world import World, dump_tables


async def test_committed_writes_stay(
    session_factory: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with SqlAlchemyProjectionTransaction(session_factory, world.registry) as tx:
        await tx.store.save_overview(overview())
        await tx.commit()
    assert len((await dump_tables(session_factory))["projector_application_overview"]) == 1


async def test_leaving_without_commit_rolls_back(
    session_factory: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with SqlAlchemyProjectionTransaction(session_factory, world.registry) as tx:
        await tx.store.save_overview(overview())
    assert (await dump_tables(session_factory))["projector_application_overview"] == []


async def test_facades_come_from_the_registry(
    session_factory: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with SqlAlchemyProjectionTransaction(session_factory, world.registry) as tx:
        assert tx.facades(ProductsFacade) is world.products  # type: ignore[type-abstract]


async def test_nothing_to_commit_outside_the_block(
    session_factory: async_sessionmaker[AsyncSession], world: World
) -> None:
    tx = SqlAlchemyProjectionTransaction(session_factory, world.registry)
    with pytest.raises(RuntimeError, match="not entered"):
        await tx.commit()
