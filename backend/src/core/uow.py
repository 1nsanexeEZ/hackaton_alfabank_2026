from types import TracebackType
from typing import Protocol, Self

from sqlalchemy.ext.asyncio import AsyncSession

_ACTIVE = "unit_of_work_active"


class UnitOfWork(Protocol):
    """Transaction boundary of a use case: everything the use case changed
    (aggregates, outbox records) is committed together or not at all.
    Leaving the block without commit() rolls back."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def __aenter__(self) -> Self:
        if self._session.info.get(_ACTIVE):
            raise RuntimeError("Nested unit of work is not supported")
        self._session.info[_ACTIVE] = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            # no-op after commit(), otherwise discards uncommitted changes
            await self._session.rollback()
        finally:
            self._session.info.pop(_ACTIVE, None)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
