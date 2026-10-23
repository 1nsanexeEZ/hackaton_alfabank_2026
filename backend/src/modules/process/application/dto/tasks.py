"""Tasks for bank employees: the facade's view (re-exported by facade.py) and
the back office API's."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from src.modules.process.application.dto.processes import ProcessViewDTO

TaskStatus = Literal["open", "in_progress", "done", "cancelled"]
# The queue filter of the back office: "active" — open and in progress.
TaskQueueStatus = Literal["active", "open", "in_progress", "done", "cancelled"]


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


@dataclass(frozen=True, slots=True)
class TaskDTO:
    """A task for the back office API: whether it is overdue is decided now."""

    id: UUID
    process_id: UUID
    application_id: UUID
    type: str
    candidate_role: str
    status: TaskStatus
    assignee_id: UUID | None
    form_schema: dict[str, Any]
    created_at: datetime
    due_at: datetime | None
    overdue: bool
    result: dict[str, Any] | None
    completed_by: UUID | None


@dataclass(frozen=True, slots=True)
class TaskDetailDTO:
    task: TaskDTO
    process: ProcessViewDTO | None
