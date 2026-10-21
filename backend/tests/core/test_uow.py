from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.messaging.inbox import InboxRecord, SqlAlchemyInboxGuard
from src.core.uow import SqlAlchemyUnitOfWork


async def count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return (await session.execute(select(func.count()).select_from(InboxRecord))).scalar_one()


async def test_commit_persists(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, SqlAlchemyUnitOfWork(session) as uow:
        await SqlAlchemyInboxGuard(session, FrozenClock()).mark("test", uuid4())
        await uow.commit()
    assert await count(session_factory) == 1


async def test_leaving_without_commit_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, SqlAlchemyUnitOfWork(session):
        await SqlAlchemyInboxGuard(session, FrozenClock()).mark("test", uuid4())
        await session.flush()
    assert await count(session_factory) == 0


async def test_exception_rolls_back(session_factory: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(RuntimeError):
        async with session_factory() as session, SqlAlchemyUnitOfWork(session):
            await SqlAlchemyInboxGuard(session, FrozenClock()).mark("test", uuid4())
            await session.flush()
            raise RuntimeError("use case failed")
    assert await count(session_factory) == 0


async def test_nested_unit_of_work_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, SqlAlchemyUnitOfWork(session):
        with pytest.raises(RuntimeError, match="Nested"):
            async with SqlAlchemyUnitOfWork(session):
                pass
    # the flag is cleared on exit: the session can be used again
    async with session_factory() as session, SqlAlchemyUnitOfWork(session) as uow:
        assert uow.session is session
