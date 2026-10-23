"""Applications outside a request and a HandlerContext (the offer expiry job):
a session of its own, the repository and the outbox bound to it."""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.core.domain.clock import Clock
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.interfaces.transactions import (
    ApplicationTransaction,
    StaleApplicationError,
)
from src.modules.applications.application.mappers.messages import PRODUCER
from src.modules.applications.infrastructure.repositories.applications import (
    SqlAlchemyApplicationRepository,
)


class _Bound:
    """What one transaction works with. The repository keeps the rows it read
    until the save, so it is built once per transaction."""

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.applications = SqlAlchemyApplicationRepository(session)
        self.outbox = SqlAlchemyOutboxWriter(session, PRODUCER, clock)


class SqlAlchemyApplicationTransaction(ApplicationTransaction):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._stack = AsyncExitStack()
        self._uow: SqlAlchemyUnitOfWork | None = None
        self._bound: _Bound | None = None

    async def __aenter__(self) -> Self:
        session = await self._stack.enter_async_context(self._session_factory())
        self._uow = await self._stack.enter_async_context(SqlAlchemyUnitOfWork(session))
        self._bound = _Bound(session, self._clock)
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
            raise StaleApplicationError(str(exc)) from exc

    async def commit(self) -> None:
        await self._entered().commit()

    async def rollback(self) -> None:
        await self._entered().rollback()

    @property
    def applications(self) -> ApplicationRepository:
        return self._objects().applications

    @property
    def outbox(self) -> MessageOutbox:
        return self._objects().outbox

    def _objects(self) -> _Bound:
        if self._bound is None:
            raise RuntimeError("The application transaction is not entered")
        return self._bound

    def _entered(self) -> SqlAlchemyUnitOfWork:
        if self._uow is None:
            raise RuntimeError("The application transaction is not entered")
        return self._uow
