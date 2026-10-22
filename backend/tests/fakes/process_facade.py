from uuid import UUID

from src.modules.process.facade import ProcessViewDTO, UserTaskDTO


class FakeProcessFacade:
    def __init__(self) -> None:
        self.views: dict[UUID, ProcessViewDTO] = {}
        self.tasks: dict[UUID, UserTaskDTO] = {}

    def add_view(self, view: ProcessViewDTO) -> ProcessViewDTO:
        self.views[view.application_id] = view
        return view

    def add_task(self, task: UserTaskDTO) -> UserTaskDTO:
        self.tasks[task.id] = task
        return task

    async def get_process_view(self, application_id: UUID) -> ProcessViewDTO | None:
        return self.views.get(application_id)

    async def list_open_tasks(
        self, role: str, limit: int = 50, offset: int = 0
    ) -> list[UserTaskDTO]:
        open_tasks = [
            t
            for t in self.tasks.values()
            if t.candidate_role == role and t.status in ("open", "in_progress")
        ]
        return open_tasks[offset : offset + limit]

    async def get_task(self, task_id: UUID) -> UserTaskDTO | None:
        return self.tasks.get(task_id)
