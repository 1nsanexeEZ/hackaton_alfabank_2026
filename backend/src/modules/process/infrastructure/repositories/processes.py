from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.serialization import from_jsonable
from src.modules.process.application.interfaces.repositories import ProcessRepository
from src.modules.process.domain.context import ProcessContext
from src.modules.process.domain.enums import ProcessStatus, WaitKind
from src.modules.process.domain.process import ProcessInstance
from src.modules.process.domain.workflow import WorkflowDefinition
from src.modules.process.infrastructure.bpmn import parse_bpmn
from src.modules.process.infrastructure.database.models import (
    ProcessRecord,
    WorkflowDefinitionRecord,
)
from src.modules.process.infrastructure.repositories.mappers import (
    apply_process,
    aware,
    step_in,
    token_in,
)

# Parsed graphs by source hash: the same few routes for every process.
_GRAPHS: dict[str, WorkflowDefinition] = {}


class SqlAlchemyProcessRepository(ProcessRepository):
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
            created_at=aware(record.created_at),  # type: ignore[arg-type]
            status=ProcessStatus(record.status),
            waiting=token_in(record.waiting),
            iterations=dict(record.iterations),
            steps=[step_in(s) for s in record.steps],
            finished_at=aware(record.finished_at),
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
            # No ORM relationship between the two: the snapshot must reach the
            # database before the process row that references it.
            await self._session.flush()
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
        apply_process(process, record, now)
        self._session.add(record)
        await self._session.flush()
        self._records[process.id] = record
        process.version = record.version

    async def save(self, process: ProcessInstance, now: datetime) -> None:
        record = self._records[process.id]
        apply_process(process, record, now)
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
