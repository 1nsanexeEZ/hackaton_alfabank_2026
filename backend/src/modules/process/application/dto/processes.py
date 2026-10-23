"""Where an application is in the bank's route. Re-exported by facade.py."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

ProcessStatus = Literal["running", "waiting", "completed", "failed", "cancelled"]


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
