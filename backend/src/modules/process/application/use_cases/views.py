"""Reads of the process and its tasks: for the facade and the back office API."""

from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.modules.process.application.dto.processes import ProcessViewDTO
from src.modules.process.application.dto.tasks import UserTaskDTO
from src.modules.process.application.interfaces.repositories import (
    ProcessRepository,
    TaskRepository,
)
from src.modules.process.application.mappers.views import process_view, task_dto
from src.modules.process.domain.enums import ACTIVE_TASK_STATUSES


class GetProcessViewUseCase:
    def __init__(self, processes: ProcessRepository) -> None:
        self._processes = processes

    async def execute(self, application_id: UUID) -> ProcessViewDTO | None:
        process = await self._processes.get_by_application(application_id)
        return process_view(process) if process else None


class GetProcessUseCase:
    """The same view for the back office API: no process is 404."""

    def __init__(self, processes: ProcessRepository) -> None:
        self._processes = processes

    async def execute(self, application_id: UUID) -> ProcessViewDTO:
        process = await self._processes.get_by_application(application_id)
        if process is None:
            raise NotFoundError("Process not found")
        return process_view(process)


class ListOpenTasksUseCase:
    def __init__(self, tasks: TaskRepository) -> None:
        self._tasks = tasks

    async def execute(self, role: str, limit: int, offset: int) -> list[UserTaskDTO]:
        tasks = await self._tasks.search(role, ACTIVE_TASK_STATUSES, limit, offset)
        return [task_dto(task) for task in tasks]


class GetTaskUseCase:
    def __init__(self, tasks: TaskRepository) -> None:
        self._tasks = tasks

    async def execute(self, task_id: UUID) -> UserTaskDTO | None:
        task = await self._tasks.get(task_id)
        return task_dto(task) if task else None
