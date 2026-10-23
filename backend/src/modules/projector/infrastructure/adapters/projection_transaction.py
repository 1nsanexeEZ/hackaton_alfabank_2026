"""The projection outside a HandlerContext (the rebuild): a session of its own,
the store and the neighbours' facades bound to it."""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.facades import FacadeRegistry
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.projector.application.interfaces.neighbours import FacadeLookup
from src.modules.projector.application.interfaces.repositories import ReadModelStore
from src.modules.projector.application.interfaces.transactions import ProjectionTransaction
from src.modules.projector.infrastructure.repositories.read_model_store import (
    SqlAlchemyReadModelStore,
)


class SessionFacades(FacadeLookup):
    """Facades bound to one session, for code that runs outside a HandlerContext."""

    def __init__(self, registry: FacadeRegistry, session: AsyncSession) -> None:
        self._registry = registry
        self._session = session

    def __call__[T](self, key: type[T]) -> T:
        return self._registry.get(key, self._session)


class SqlAlchemyProjectionTransaction(ProjectionTransaction):
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], facades: FacadeRegistry
    ) -> None:
        self._session_factory = session_factory
        self._registry = facades
        self._stack = AsyncExitStack()
        self._uow: SqlAlchemyUnitOfWork | None = None

    async def __aenter__(self) -> Self:
        session = await self._stack.enter_async_context(self._session_factory())
        self._uow = await self._stack.enter_async_context(SqlAlchemyUnitOfWork(session))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._uow = None
        # Rolls back what was not committed, then closes the session.
        await self._stack.__aexit__(exc_type, exc, tb)

    async def commit(self) -> None:
        await self._entered().commit()

    async def rollback(self) -> None:
        await self._entered().rollback()

    @property
    def store(self) -> ReadModelStore:
        return SqlAlchemyReadModelStore(self._entered().session)

    @property
    def facades(self) -> FacadeLookup:
        return SessionFacades(self._registry, self._entered().session)

    def _entered(self) -> SqlAlchemyUnitOfWork:
        if self._uow is None:
            raise RuntimeError("The projection transaction is not entered")
        return self._uow
