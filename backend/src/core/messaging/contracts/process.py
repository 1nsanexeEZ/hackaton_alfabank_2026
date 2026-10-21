"""process.events — key: application_id."""

from datetime import datetime
from typing import Any
from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage


class ProcessStarted(IntegrationMessage):
    TYPE = "ProcessStarted"
    TOPIC = topics.PROCESS_EVENTS

    process_id: UUID
    application_id: UUID
    workflow_code: str


class StepCompleted(IntegrationMessage):
    TYPE = "StepCompleted"
    TOPIC = topics.PROCESS_EVENTS

    process_id: UUID
    application_id: UUID
    node_id: str
    step_code: str
    # Human label of the stage for the client ("Проверяем данные о компании").
    client_stage: str | None = None


class UserTaskCreated(IntegrationMessage):
    TYPE = "UserTaskCreated"
    TOPIC = topics.PROCESS_EVENTS

    task_id: UUID
    process_id: UUID
    application_id: UUID
    task_type: str
    candidate_role: str
    due_at: datetime | None = None


class UserTaskCompleted(IntegrationMessage):
    TYPE = "UserTaskCompleted"
    TOPIC = topics.PROCESS_EVENTS

    task_id: UUID
    application_id: UUID
    completed_by: UUID
    result: dict[str, Any] = {}


class ProcessCompleted(IntegrationMessage):
    TYPE = "ProcessCompleted"
    TOPIC = topics.PROCESS_EVENTS

    process_id: UUID
    application_id: UUID
    outcome: str


class ProcessFailed(IntegrationMessage):
    TYPE = "ProcessFailed"
    TOPIC = topics.PROCESS_EVENTS

    process_id: UUID
    application_id: UUID
    reason: str
