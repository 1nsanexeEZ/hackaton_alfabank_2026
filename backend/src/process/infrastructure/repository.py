from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.serialization import from_jsonable, to_jsonable
from src.process.domain.context import ProcessContext
from src.process.domain.process import (
    ProcessInstance,
    ProcessStatus,
    StepExecution,
    WaitKind,
    WaitToken,
)
from src.process.domain.steps import StepKind
from src.process.domain.tasks import TaskStatus, UserTask
from src.process.domain.workflow import WorkflowDefinition
from src.process.infrastructure.bpmn import parse_bpmn
from src.process.infrastructure.models import (
    ProcessRecord,
    StepExecutionRecord,
    UserTaskRecord,
    WorkflowDefinitionRecord,
)

# Parsed graphs by source hash: the same few routes for every process.
_GRAPHS: dict[str, WorkflowDefinition] = {}


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _token_out(token: WaitToken | None) -> dict[str, Any] | None:
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


def _token_in(data: dict[str, Any] | None) -> WaitToken | None:
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


class SqlAlchemyProcessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._records: dict[UUID, ProcessRecord] = {}

    async def get_by_application(
        self, application_id: UUID, for_update: bool = False
    ) -> ProcessInstance | None:
        stmt = select(ProcessRecord).where(ProcessRecord.application_id == application_id)
        if for_update:
            # Replies of different modules for one application are serialized here.
            stmt = stmt.with_for_update()
        record = (await self._session.scalars(stmt)).one_or_none()
        if record is None:
            return None
        self._records[record.id] = record
        return ProcessInstance(
            id=record.id,
            application_id=record.application_id,
            workflow=await self._graph(record.workflow_hash),
            context=from_jsonable(ProcessContext, record.context),
            current_node_id=record.current_node_id,
            created_at=_aware(record.created_at),  # type: ignore[arg-type]
            status=ProcessStatus(record.status),
            waiting=_token_in(record.waiting),
            iterations=dict(record.iterations),
            steps=[_step_in(s) for s in record.steps],
            finished_at=_aware(record.finished_at),
            version=record.version,
        )

    async def add(self, process: ProcessInstance, source: bytes, now: datetime) -> None:
        workflow = process.workflow
        if await self._session.get(WorkflowDefinitionRecord, workflow.source_hash) is None:
            self._session.add(
                WorkflowDefinitionRecord(
                    source_hash=workflow.source_hash,
                    code=workflow.code,
                    version=workflow.version,
                    source=source.decode("utf-8"),
                    created_at=now,
                )
            )
        _GRAPHS.setdefault(workflow.source_hash, workflow)
        record = ProcessRecord(
            id=process.id,
            application_id=process.application_id,
            workflow_code=workflow.code,
            workflow_version=workflow.version,
            workflow_hash=workflow.source_hash,
            created_at=process.created_at,
            steps=[],
        )
        self._apply(process, record, now)
        self._session.add(record)
        await self._session.flush()
        self._records[process.id] = record
        process.version = record.version

    async def save(self, process: ProcessInstance, now: datetime) -> None:
        record = self._records[process.id]
        self._apply(process, record, now)
        await self._session.flush()
        process.version = record.version

    async def waiting_for_replies_since(self, moment: datetime, limit: int) -> list[UUID]:
        stmt = (
            select(ProcessRecord.application_id, ProcessRecord.waiting)
            .where(
                ProcessRecord.status == ProcessStatus.WAITING.value,
                ProcessRecord.waiting_since <= moment,
            )
            .order_by(ProcessRecord.waiting_since)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            application_id
            for application_id, waiting in rows
            if waiting and waiting["kind"] == WaitKind.COMMAND_REPLY.value
        ]

    async def _graph(self, source_hash: str) -> WorkflowDefinition:
        graph = _GRAPHS.get(source_hash)
        if graph is None:
            record = await self._session.get(WorkflowDefinitionRecord, source_hash)
            if record is None:
                raise LookupError(f"Route snapshot {source_hash} is missing")
            graph = parse_bpmn(record.source.encode("utf-8"))
            _GRAPHS[source_hash] = graph
        return graph

    @staticmethod
    def _apply(process: ProcessInstance, record: ProcessRecord, now: datetime) -> None:
        record.status = process.status.value
        record.current_node_id = process.current_node_id
        record.waiting = _token_out(process.waiting)
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


def _step_in(row: StepExecutionRecord) -> StepExecution:
    return StepExecution(
        id=row.id,
        node_id=row.node_id,
        step_code=row.step_code,
        kind=StepKind(row.kind),
        iteration=row.iteration,
        started_at=_aware(row.started_at),  # type: ignore[arg-type]
        finished_at=_aware(row.finished_at),
        outcome=row.outcome,
        command_event_id=row.command_event_id,
        error=row.error,
    )


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._records: dict[UUID, UserTaskRecord] = {}

    async def add(self, task: UserTask) -> None:
        record = UserTaskRecord(
            id=task.id,
            process_id=task.process_id,
            application_id=task.application_id,
            node_id=task.node_id,
            type=task.type,
            candidate_role=task.candidate_role,
            form_schema=dict(task.form_schema),
            created_at=task.created_at,
            due_at=task.due_at,
        )
        self._apply(task, record)
        self._session.add(record)
        await self._session.flush()
        self._records[task.id] = record
        task.version = record.version

    async def get(self, task_id: UUID) -> UserTask | None:
        record = await self._session.get(UserTaskRecord, task_id)
        if record is None:
            return None
        self._records[record.id] = record
        return _task_in(record)

    async def save(self, task: UserTask) -> None:
        record = self._records[task.id]
        self._apply(task, record)
        await self._session.flush()
        task.version = record.version

    async def search(
        self, role: str | None, statuses: Sequence[str], limit: int, offset: int
    ) -> list[UserTask]:
        stmt = select(UserTaskRecord).where(UserTaskRecord.status.in_(list(statuses)))
        if role is not None:
            stmt = stmt.where(UserTaskRecord.candidate_role == role)
        stmt = stmt.order_by(UserTaskRecord.due_at, UserTaskRecord.created_at)
        records = (await self._session.scalars(stmt.limit(limit).offset(offset))).all()
        for record in records:
            self._records[record.id] = record
        return [_task_in(r) for r in records]

    async def active_of_process(self, process_id: UUID) -> list[UserTask]:
        stmt = select(UserTaskRecord).where(
            UserTaskRecord.process_id == process_id,
            UserTaskRecord.status.in_([TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]),
        )
        records = (await self._session.scalars(stmt)).all()
        for record in records:
            self._records[record.id] = record
        return [_task_in(r) for r in records]

    @staticmethod
    def _apply(task: UserTask, record: UserTaskRecord) -> None:
        record.status = task.status.value
        record.assignee_id = task.assignee_id
        record.result = dict(task.result) if task.result is not None else None
        record.completed_by = task.completed_by
        record.completed_at = task.completed_at


def _task_in(record: UserTaskRecord) -> UserTask:
    return UserTask(
        id=record.id,
        process_id=record.process_id,
        application_id=record.application_id,
        node_id=record.node_id,
        type=record.type,
        candidate_role=record.candidate_role,
        form_schema=dict(record.form_schema),
        created_at=_aware(record.created_at),  # type: ignore[arg-type]
        due_at=_aware(record.due_at),
        status=TaskStatus(record.status),
        assignee_id=record.assignee_id,
        result=dict(record.result) if record.result is not None else None,
        completed_by=record.completed_by,
        completed_at=_aware(record.completed_at),
        version=record.version,
    )
