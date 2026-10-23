"""The engine outside a HandlerContext (the timeout job): a session of its own,
the repositories, the outbox and the facts bound to it."""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.process.application.interfaces.outbox import MessageOutbox
from src.modules.process.application.interfaces.repositories import (
    ProcessRepository,
    TaskRepository,
)
from src.modules.process.application.interfaces.transactions import (
    ProcessTransaction,
    StaleProcessError,
)
from src.modules.process.application.mappers.messages import PRODUCER
from src.modules.process.domain.steps import ProcessFacts
from src.modules.process.infrastructure.adapters.application_facts import ApplicationFacts
from src.modules.process.infrastructure.repositories.processes import (
    SqlAlchemyProcessRepository,
)
from src.modules.process.infrastructure.repositories.tasks import SqlAlchemyTaskRepository


class _Bound:
    """What one transaction works with. The repositories keep the rows they
    read until the save, so they are built once per transaction; the facts
    — on first use."""

    def __init__(self, session: AsyncSession, facades: FacadeRegistry, clock: Clock) -> None:
        self.session = session
        self.registry = facades
        self.processes = SqlAlchemyProcessRepository(session)
        self.tasks = SqlAlchemyTaskRepository(session)
        self.outbox = SqlAlchemyOutboxWriter(session, PRODUCER, clock)
        self.facts: ApplicationFacts | None = None


class SqlAlchemyProcessTransaction(ProcessTransaction):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        facades: FacadeRegistry,
        clock: Clock,
    ) -> None:
        self._session_factory = session_factory
        self._registry = facades
        self._clock = clock
        self._stack = AsyncExitStack()
        self._uow: SqlAlchemyUnitOfWork | None = None
        self._bound: _Bound | None = None

    async def __aenter__(self) -> Self:
        session = await self._stack.enter_async_context(self._session_factory())
        self._uow = await self._stack.enter_async_context(SqlAlchemyUnitOfWork(session))
        self._bound = _Bound(session, self._registry, self._clock)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._uow = None
        self._bound = None
        # Rolls back what was not committed, then closes the session.
        await self._stack.__aexit__(exc_type, exc, tb)
        if isinstance(exc, StaleDataError):
            raise StaleProcessError(str(exc)) from exc

    async def commit(self) -> None:
        await self._entered().commit()

    async def rollback(self) -> None:
        await self._entered().rollback()

    @property
    def processes(self) -> ProcessRepository:
        return self._objects().processes

    @property
    def tasks(self) -> TaskRepository:
        return self._objects().tasks

    @property
    def outbox(self) -> MessageOutbox:
        return self._objects().outbox

    @property
    def facts(self) -> ProcessFacts:
        bound = self._objects()
        if bound.facts is None:
            bound.facts = ApplicationFacts(
                bound.registry.get(ApplicationsFacade, bound.session),
                bound.registry.get(ClientsFacade, bound.session),
                bound.registry.get(IdentityFacade, bound.session),
            )
        return bound.facts

    def _objects(self) -> _Bound:
        if self._bound is None:
            raise RuntimeError("The process transaction is not entered")
        return self._bound

    def _entered(self) -> SqlAlchemyUnitOfWork:
        if self._uow is None:
            raise RuntimeError("The process transaction is not entered")
        return self._uow
