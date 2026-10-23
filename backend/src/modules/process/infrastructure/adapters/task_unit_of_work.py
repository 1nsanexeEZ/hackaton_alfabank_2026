from sqlalchemy.orm.exc import StaleDataError

from src.core.exceptions.exceptions import ConflictError
from src.core.uow import SqlAlchemyUnitOfWork


class TaskUnitOfWork(SqlAlchemyUnitOfWork):
    """The unit of work of the task endpoints: a task changed by someone else
    since it was read fails the commit with 409."""

    async def commit(self) -> None:
        try:
            await super().commit()
        except StaleDataError:
            await self.rollback()
            raise ConflictError(
                "The task was changed by someone else", details={"code": "version_conflict"}
            ) from None
