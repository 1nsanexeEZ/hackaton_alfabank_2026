from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str
    step_code: str | None
    kind: str
    iteration: int
    started_at: datetime
    finished_at: datetime | None
    outcome: str | None
    client_stage: str | None
    error: str | None


class ProcessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    process_id: UUID
    application_id: UUID
    workflow_code: str
    workflow_version: int
    status: str
    current_node_id: str | None
    client_stage: str | None
    # Node ids already passed — to highlight the path on the diagram.
    visited_node_ids: list[str]
    steps: list[StepOut]
    started_at: datetime
    finished_at: datetime | None
