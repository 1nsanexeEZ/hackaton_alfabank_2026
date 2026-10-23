"""ProcessFacade for other modules. Only calls the use cases, no logic of its own.
Built per session: reads join the caller's transaction."""

from uuid import UUID

from src.modules.process.application.dto.processes import ProcessViewDTO
from src.modules.process.application.dto.tasks import UserTaskDTO
from src.modules.process.application.use_cases.views import (
    GetProcessViewUseCase,
    GetTaskUseCase,
    ListOpenTasksUseCase,
)
from src.modules.process.facade import ProcessFacade


class ProcessFacadeImpl(ProcessFacade):
    def __init__(
        self,
        get_process_view: GetProcessViewUseCase,
        list_open_tasks: ListOpenTasksUseCase,
        get_task: GetTaskUseCase,
    ) -> None:
        self._get_process_view = get_process_view
        self._list_open_tasks = list_open_tasks
        self._get_task = get_task

    async def get_process_view(self, application_id: UUID) -> ProcessViewDTO | None:
        return await self._get_process_view.execute(application_id)

    async def list_open_tasks(
        self, role: str, limit: int = 50, offset: int = 0
    ) -> list[UserTaskDTO]:
        return await self._list_open_tasks.execute(role, limit, offset)

    async def get_task(self, task_id: UUID) -> UserTaskDTO | None:
        return await self._get_task.execute(task_id)
