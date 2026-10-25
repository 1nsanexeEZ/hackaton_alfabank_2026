"""ORM rows <-> domain objects of the engine."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.core.serialization import to_jsonable
from src.modules.process.domain.enums import StepKind, TaskStatus, WaitKind
from src.modules.process.domain.process import ProcessInstance, StepExecution, WaitToken
from src.modules.process.domain.tasks import UserTask
from src.modules.process.infrastructure.database.models import (
    ProcessRecord,
    StepExecutionRecord,
    UserTaskRecord,
)


def aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def token_out(token: WaitToken | None) -> dict[str, Any] | None:
    if token is None:
        return None
    return {
        "kind": token.kind.value,
        "node_id": token.node_id,
        "expected_types": sorted(token.expected_types),
        "since": token.since.isoformat(),
        "command_event_id": str(token.command_event_id) if token.command_event_id else None,
        "task_id": str(token.task_id) if token.task_id else None,
    }


def token_in(data: dict[str, Any] | None) -> WaitToken | None:
    if data is None:
        return None
    return WaitToken(
        kind=WaitKind(data["kind"]),
        node_id=data["node_id"],
        expected_types=frozenset(data["expected_types"]),
        since=datetime.fromisoformat(data["since"]),
        command_event_id=UUID(data["command_event_id"]) if data["command_event_id"] else None,
        task_id=UUID(data["task_id"]) if data["task_id"] else None,
    )


def apply_process(process: ProcessInstance, record: ProcessRecord, now: datetime) -> None:
    record.status = process.status.value
    record.current_node_id = process.current_node_id
    record.waiting = token_out(process.waiting)
    record.waiting_since = process.waiting.since if process.waiting else None
    record.context = to_jsonable(process.context)
    record.iterations = dict(process.iterations)
    record.updated_at = now
    record.finished_at = process.finished_at
    rows = {row.id: row for row in record.steps}
    for step in process.steps:
        row = rows.get(step.id)
        if row is None:
            row = StepExecutionRecord(id=step.id, process_id=process.id)
            record.steps.append(row)
        row.node_id = step.node_id
        row.step_code = step.step_code
        row.kind = step.kind.value
        row.iteration = step.iteration
        row.started_at = step.started_at
        row.finished_at = step.finished_at
        row.outcome = step.outcome
        row.command_event_id = step.command_event_id
        row.error = step.error


def step_in(row: StepExecutionRecord) -> StepExecution:
    return StepExecution(
        id=row.id,
        node_id=row.node_id,
        step_code=row.step_code,
        kind=StepKind(row.kind),
        iteration=row.iteration,
        started_at=aware(row.started_at),  # type: ignore[arg-type]
        finished_at=aware(row.finished_at),
        outcome=row.outcome,
        command_event_id=row.command_event_id,
        error=row.error,
    )


def apply_task(task: UserTask, record: UserTaskRecord) -> None:
    record.status = task.status.value
    record.assignee_id = task.assignee_id
    record.result = dict(task.result) if task.result is not None else None
    record.completed_by = task.completed_by
    record.completed_at = task.completed_at


def task_in(record: UserTaskRecord) -> UserTask:
    return UserTask(
        id=record.id,
        process_id=record.process_id,
        application_id=record.application_id,
        node_id=record.node_id,
        type=record.type,
        candidate_role=record.candidate_role,
        form_schema=dict(record.form_schema),
        created_at=aware(record.created_at),  # type: ignore[arg-type]
        due_at=aware(record.due_at),
        reason=record.reason,
        status=TaskStatus(record.status),
        assignee_id=record.assignee_id,
        result=dict(record.result) if record.result is not None else None,
        completed_by=record.completed_by,
        completed_at=aware(record.completed_at),
        version=record.version,
    )
