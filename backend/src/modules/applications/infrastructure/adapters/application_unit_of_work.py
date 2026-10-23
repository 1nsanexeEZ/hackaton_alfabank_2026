from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from src.core.exceptions.exceptions import ConflictError
from src.core.uow import SqlAlchemyUnitOfWork


class ApplicationUnitOfWork(SqlAlchemyUnitOfWork):
    """The unit of work of the applications API. A write the database refuses
    leaves the block as 409 after the rollback, whether it fails on flush or
    on commit:
    - the application was changed by someone else since it was read (version);
    - the company already has an active application for this product (the
      partial unique index)."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await super().__aexit__(exc_type, exc, tb)
        if isinstance(exc, StaleDataError):
            raise ConflictError(
                "Application was changed by someone else, reload it",
                details={"code": "version_conflict"},
            ) from None
        if isinstance(exc, IntegrityError):
            raise ConflictError(
                "The company already has an active application for this product",
                details={"code": "duplicate_active"},
            ) from None
