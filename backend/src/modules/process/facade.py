"""Process contract: where an application is in the bank's route and what
tasks are waiting for people."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

ProcessStatus = Literal["running", "waiting", "completed", "failed", "cancelled"]
TaskStatus = Literal["open", "in_progress", "done", "cancelled"]


@dataclass(frozen=True, slots=True)
class StepViewDTO:
    node_id: str
    step_code: str | None
    kind: Literal["immediate", "async", "stoppable"]
    iteration: int
    started_at: datetime
    finished_at: datetime | None
    outcome: str | None
    client_stage: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessViewDTO:
    process_id: UUID
    application_id: UUID
    workflow_code: str
    workflow_version: int
    status: ProcessStatus
    current_node_id: str | None
    client_stage: str | None
    # Node ids already passed, in order — to highlight the path on the diagram.
    visited_node_ids: tuple[str, ...]
    steps: tuple[StepViewDTO, ...]
    started_at: datetime
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserTaskDTO:
    id: UUID
    process_id: UUID
    application_id: UUID
    node_id: str
    type: str
    candidate_role: str
    assignee_id: UUID | None
    status: TaskStatus
    form_schema: dict[str, Any]
    created_at: datetime
    due_at: datetime | None
    result: dict[str, Any] | None = None
    completed_by: UUID | None = None


class ProcessFacade(Protocol):
    async def get_process_view(self, application_id: UUID) -> ProcessViewDTO | None: ...

    async def list_open_tasks(
        self, role: str, limit: int = 50, offset: int = 0
    ) -> list[UserTaskDTO]: ...

    async def get_task(self, task_id: UUID) -> UserTaskDTO | None: ...
