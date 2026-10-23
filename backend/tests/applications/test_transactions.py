"""Transactions of applications: the offer expiry job's own session and the
unit of work of the API, which turns a write the database refuses into 409."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import ConflictError, NotFoundError
from src.modules.applications.application.interfaces.transactions import StaleApplicationError
from src.modules.applications.infrastructure.adapters.application_transaction import (
    SqlAlchemyApplicationTransaction,
)
from src.modules.applications.infrastructure.adapters.application_unit_of_work import (
    ApplicationUnitOfWork,
)
from src.modules.applications.infrastructure.repositories.applications import (
    SqlAlchemyApplicationRepository,
)
from tests.applications.unit.factories import NOW, draft


def _transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlAlchemyApplicationTransaction:
    return SqlAlchemyApplicationTransaction(session_factory, FrozenClock(NOW))


async def test_committed_application_stays(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    application = draft()
    async with _transaction(session_factory) as tx:
        await tx.applications.add(application)
        await tx.commit()
    async with _transaction(session_factory) as tx:
        stored = await tx.applications.get(application.id)
    assert stored.number == application.number


async def test_leaving_without_commit_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    application = draft()
    async with _transaction(session_factory) as tx:
        assert tx.applications is tx.applications  # the rows it read are kept for the save
        await tx.applications.add(application)
    async with _transaction(session_factory) as tx:
        with pytest.raises(NotFoundError):
            await tx.applications.get(application.id)


async def test_a_concurrent_change_leaves_as_stale_application(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(StaleApplicationError):
        async with _transaction(session_factory):
            raise StaleDataError("UPDATE statement on table 'applications' matched 0 rows")


async def test_nothing_to_commit_outside_the_block(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tx = _transaction(session_factory)
    with pytest.raises(RuntimeError, match="not entered"):
        await tx.commit()
    with pytest.raises(RuntimeError, match="not entered"):
        _ = tx.outbox


class _StaleSession:
    """A session whose commit meets a row changed by someone else."""

    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.rollbacks = 0

    async def commit(self) -> None:
        raise StaleDataError("UPDATE statement on table 'applications' matched 0 rows")

    async def rollback(self) -> None:
        self.rollbacks += 1


async def test_a_stale_application_fails_with_409() -> None:
    session = _StaleSession()
    uow = ApplicationUnitOfWork(session)  # type: ignore[arg-type]
    with pytest.raises(ConflictError) as error:
        async with uow:
            await uow.commit()
    assert error.value.details == {"code": "version_conflict"}
    assert session.rollbacks >= 1


async def test_a_second_active_application_fails_with_409(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        uow = ApplicationUnitOfWork(session)
        async with uow:
            await SqlAlchemyApplicationRepository(session).add(draft())
            await uow.commit()
        with pytest.raises(ConflictError) as error:
            async with uow:
                # the same company and product: the partial unique index refuses it
                await SqlAlchemyApplicationRepository(session).add(draft())
                await uow.commit()
    assert error.value.details == {"code": "duplicate_active"}
