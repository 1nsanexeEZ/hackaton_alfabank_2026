"""Domain events and commands of the engine -> integration messages, incoming
messages -> triggers (the domain does not know the contracts)."""

from uuid import UUID

from src.core.messaging.contracts import process as contracts
from src.core.messaging.contracts.base import IntegrationMessage, get_contract
from src.modules.process.domain.events import (
    ProcessCompleted,
    ProcessEvent,
    ProcessFailed,
    ProcessStarted,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.modules.process.domain.steps import CommandRequest, Trigger

PRODUCER = "process"


def command_contract(request: CommandRequest) -> IntegrationMessage:
    return get_contract(request.type).model_validate(dict(request.payload))


def to_contract(event: ProcessEvent) -> IntegrationMessage:
    ids = {"process_id": event.process_id, "application_id": event.application_id}
    match event:
        case ProcessStarted():
            return contracts.ProcessStarted(**ids, workflow_code=event.workflow_code)
        case StepCompleted():
            return contracts.StepCompleted(
                **ids,
                node_id=event.node_id,
                step_code=event.step_code,
                client_stage=event.client_stage,
            )
        case UserTaskCreated():
            return contracts.UserTaskCreated(
                **ids,
                task_id=event.task_id,
                task_type=event.task_type,
                candidate_role=event.candidate_role,
                due_at=event.due_at,
            )
        case UserTaskCompleted():
            return contracts.UserTaskCompleted(
                task_id=event.task_id,
                application_id=event.application_id,
                completed_by=event.completed_by,
                result=dict(event.result),
            )
        case ProcessCompleted():
            return contracts.ProcessCompleted(**ids, outcome=event.outcome)
        case ProcessFailed():
            return contracts.ProcessFailed(**ids, reason=event.reason)
    raise TypeError(f"No integration contract for {type(event).__name__}")


def trigger(message: IntegrationMessage, causation_id: UUID | None = None) -> Trigger:
    """A client event or a reply as what the process may be waiting for; a
    reply carries `causation_id` — the id of the command it answers."""
    return Trigger(message.TYPE, message.model_dump(), causation_id=causation_id)
