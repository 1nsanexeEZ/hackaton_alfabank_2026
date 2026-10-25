from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.process.application.interfaces.repositories import TaskRepository
from src.modules.process.domain.enums import ACTIVE_TASK_STATUSES
from src.modules.process.domain.tasks import UserTask
from src.modules.process.infrastructure.database.models import UserTaskRecord
from src.modules.process.infrastructure.repositories.mappers import apply_task, task_in


class SqlAlchemyTaskRepository(TaskRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._records: dict[UUID, UserTaskRecord] = {}

    async def add(self, task: UserTask) -> None:
        record = UserTaskRecord(
            id=task.id,
            process_id=task.process_id,
            application_id=task.application_id,
            node_id=task.node_id,
            type=task.type,
            candidate_role=task.candidate_role,
            form_schema=dict(task.form_schema),
            created_at=task.created_at,
            due_at=task.due_at,
            reason=task.reason,
        )
        apply_task(task, record)
        self._session.add(record)
        await self._session.flush()
        self._records[task.id] = record
        task.version = record.version

    async def get(self, task_id: UUID) -> UserTask | None:
        record = await self._session.get(UserTaskRecord, task_id)
        if record is None:
            return None
        self._records[record.id] = record
        return task_in(record)

    async def save(self, task: UserTask) -> None:
        record = self._records[task.id]
        apply_task(task, record)
        await self._session.flush()
        task.version = record.version

    async def search(
        self, role: str | None, statuses: Sequence[str], limit: int, offset: int
    ) -> list[UserTask]:
        stmt = select(UserTaskRecord).where(UserTaskRecord.status.in_(list(statuses)))
        if role is not None:
            stmt = stmt.where(UserTaskRecord.candidate_role == role)
        stmt = stmt.order_by(UserTaskRecord.due_at, UserTaskRecord.created_at)
        records = (await self._session.scalars(stmt.limit(limit).offset(offset))).all()
        for record in records:
            self._records[record.id] = record
        return [task_in(r) for r in records]

    async def active_of_process(self, process_id: UUID) -> list[UserTask]:
        stmt = select(UserTaskRecord).where(
            UserTaskRecord.process_id == process_id,
            UserTaskRecord.status.in_(ACTIVE_TASK_STATUSES),
        )
        records = (await self._session.scalars(stmt)).all()
        for record in records:
            self._records[record.id] = record
        return [task_in(r) for r in records]
