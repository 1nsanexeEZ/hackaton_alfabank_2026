"""Domain events of the process; the application layer maps them to
`process.events` contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.core.domain import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ProcessEvent(DomainEvent):
    process_id: UUID
    application_id: UUID


@dataclass(frozen=True, kw_only=True)
class ProcessStarted(ProcessEvent):
    workflow_code: str


@dataclass(frozen=True, kw_only=True)
class StepCompleted(ProcessEvent):
    node_id: str
    step_code: str
    # Set only when the stage the client sees changes: the stage the
    # application is at now.
    client_stage: str | None = None


@dataclass(frozen=True, kw_only=True)
class UserTaskCreated(ProcessEvent):
    task_id: UUID
    task_type: str
    candidate_role: str
    due_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class UserTaskCompleted(ProcessEvent):
    task_id: UUID
    completed_by: UUID
    result: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class ProcessCompleted(ProcessEvent):
    outcome: str


@dataclass(frozen=True, kw_only=True)
class ProcessFailed(ProcessEvent):
    reason: str
