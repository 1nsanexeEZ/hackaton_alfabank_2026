from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.support.application.interfaces.repositories import TicketChangedError


class SupportUnitOfWork(SqlAlchemyUnitOfWork):
    """The unit of work of the support API. A write the database refuses leaves
    the block as TicketChangedError (409) after the rollback, whether it fails
    on flush or on commit: the ticket was changed by someone else since it was
    read (version), or a concurrent message took the same place in the chat."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await super().__aexit__(exc_type, exc, tb)
        if isinstance(exc, StaleDataError | IntegrityError):
            raise TicketChangedError() from None
