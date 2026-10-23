"""Process contract: where an application is in the bank's route and what
tasks are waiting for people.

The only entry point for other modules: the protocol below and the DTO it returns
(defined in `application/dto`, re-exported here)."""

from typing import Protocol
from uuid import UUID

from src.modules.process.application.dto.processes import (
    ProcessStatus,
    ProcessViewDTO,
    StepViewDTO,
)
from src.modules.process.application.dto.tasks import TaskStatus, UserTaskDTO

__all__ = [
    "ProcessFacade",
    "ProcessStatus",
    "ProcessViewDTO",
    "StepViewDTO",
    "TaskStatus",
    "UserTaskDTO",
]


class ProcessFacade(Protocol):
    async def get_process_view(self, application_id: UUID) -> ProcessViewDTO | None: ...

    async def list_open_tasks(
        self, role: str, limit: int = 50, offset: int = 0
    ) -> list[UserTaskDTO]: ...

    async def get_task(self, task_id: UUID) -> UserTaskDTO | None: ...
