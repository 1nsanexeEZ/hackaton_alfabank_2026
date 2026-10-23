"""Transactions of the engine: the timeout job's own session and the unit of
work of the task endpoints."""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import ConflictError
from src.core.facades import FacadeRegistry
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.process.application.interfaces.transactions import StaleProcessError
from src.modules.process.domain.process import ProcessInstance
from src.modules.process.infrastructure.adapters.application_facts import ApplicationFacts
from src.modules.process.infrastructure.adapters.process_transaction import (
    SqlAlchemyProcessTransaction,
)
from src.modules.process.infrastructure.adapters.task_unit_of_work import TaskUnitOfWork
from src.modules.process.infrastructure.adapters.workflow_catalog import load_workflows
from tests.process.unit.routes import NOW, context

CODE = "express_v1"


def _transaction(
    session_factory: async_sessionmaker[AsyncSession], registry: FacadeRegistry | None = None
) -> SqlAlchemyProcessTransaction:
    return SqlAlchemyProcessTransaction(
        session_factory, registry or FacadeRegistry(), FrozenClock(NOW)
    )


def _process() -> ProcessInstance:
    workflow = load_workflows().get(CODE)
    return ProcessInstance.start(id=uuid4(), workflow=workflow, context=context(), now=NOW)


async def _stored(
    session_factory: async_sessionmaker[AsyncSession], process: ProcessInstance
) -> ProcessInstance | None:
    async with _transaction(session_factory) as tx:
        return await tx.processes.get_by_application(process.application_id)


async def test_committed_process_stays(session_factory: async_sessionmaker[AsyncSession]) -> None:
    process = _process()
    async with _transaction(session_factory) as tx:
        await tx.processes.add(process, load_workflows().source(CODE), NOW)
        await tx.commit()
    stored = await _stored(session_factory, process)
    assert stored is not None and stored.id == process.id


async def test_leaving_without_commit_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    process = _process()
    async with _transaction(session_factory) as tx:
        await tx.processes.add(process, load_workflows().source(CODE), NOW)
    assert await _stored(session_factory, process) is None


async def test_a_concurrent_change_leaves_as_stale_process(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(StaleProcessError):
        async with _transaction(session_factory):
            raise StaleDataError("UPDATE statement on table 'process_instances' matched 0 rows")


async def test_facts_are_read_on_the_transaction_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    sessions: list[AsyncSession] = []

    def factory(session: AsyncSession) -> Any:
        sessions.append(session)
        return object()

    registry = FacadeRegistry()
    for key in (ApplicationsFacade, ClientsFacade, IdentityFacade):
        registry.register(key, factory)
    async with _transaction(session_factory, registry) as tx:
        assert tx.processes is tx.processes  # the rows it read are kept for the save
        assert sessions == []  # the facts are built on first use only
        facts = tx.facts
        assert isinstance(facts, ApplicationFacts) and tx.facts is facts
    assert len(sessions) == 3 and len(set(map(id, sessions))) == 1


async def test_nothing_to_commit_outside_the_block(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tx = _transaction(session_factory)
    with pytest.raises(RuntimeError, match="not entered"):
        await tx.commit()
    with pytest.raises(RuntimeError, match="not entered"):
        _ = tx.processes


class _StaleSession:
    """A session whose commit meets a row changed by someone else."""

    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.rollbacks = 0

    async def commit(self) -> None:
        raise StaleDataError("UPDATE statement on table 'process_user_tasks' matched 0 rows")

    async def rollback(self) -> None:
        self.rollbacks += 1


async def test_a_stale_task_fails_the_commit_with_409() -> None:
    session = _StaleSession()
    uow = TaskUnitOfWork(session)  # type: ignore[arg-type]
    with pytest.raises(ConflictError) as error:
        async with uow:
            await uow.commit()
    assert error.value.details == {"code": "version_conflict"}
    assert session.rollbacks >= 1
