from dataclasses import asdict
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from src.core.access.dependencies import CurrentUserId, require_permissions
from src.core.access.permissions import Permissions
from src.core.exceptions.exceptions import ConflictError, NotFoundError
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.process.api.schemas import (
    ProcessOut,
    TaskDetailOut,
    TaskOut,
    TaskResultIn,
    WorkflowOut,
)
from src.process.application.service import ACTIVE_TASK_STATUSES, ProcessService
from src.process.domain.tasks import UserTask
from src.process.infrastructure.consumers import MODULE, build_service
from src.process.infrastructure.facade_impl import ProcessFacadeImpl, process_view
from src.process.infrastructure.repository import SqlAlchemyProcessRepository

router = APIRouter(tags=["process"])

CanRead = [Depends(require_permissions(Permissions.TASKS_READ))]
CanUpdate = [Depends(require_permissions(Permissions.TASKS_UPDATE))]


def get_service(request: Request, session: DbSession) -> ProcessService:
    state = request.app.state
    return build_service(
        session,
        SqlAlchemyOutboxWriter(session, MODULE, state.clock),
        state.facades,
        state.workflows,
        state.clock,
    )


Service = Annotated[ProcessService, Depends(get_service)]


async def commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise ConflictError(
            "The task was changed by someone else", details={"code": "version_conflict"}
        ) from None


def task_out(request: Request, task: UserTask) -> TaskOut:
    return TaskOut(
        id=task.id,
        process_id=task.process_id,
        application_id=task.application_id,
        type=task.type,
        candidate_role=task.candidate_role,
        status=task.status.value,
        assignee_id=task.assignee_id,
        form_schema=task.form_schema,
        created_at=task.created_at,
        due_at=task.due_at,
        overdue=task.is_overdue(request.app.state.clock.now()),
        result=task.result,
        completed_by=task.completed_by,
    )


@router.get("/tasks", response_model=list[TaskOut], dependencies=CanRead)
async def list_tasks(
    request: Request,
    service: Service,
    role: str | None = "underwriter",
    status: Literal["active", "open", "in_progress", "done", "cancelled"] = "active",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskOut]:
    """Underwriter queue by due date (the back office screen reads the projector)."""
    statuses = ACTIVE_TASK_STATUSES if status == "active" else [status]
    tasks = await service.list_tasks(role, statuses, limit, offset)
    return [task_out(request, task) for task in tasks]


@router.get("/tasks/{task_id}", response_model=TaskDetailOut, dependencies=CanRead)
async def get_task(task_id: UUID, request: Request, session: DbSession) -> TaskDetailOut:
    facade = ProcessFacadeImpl(session)
    task = await facade.get_task(task_id)
    if task is None:
        raise NotFoundError("Task not found")
    view = await facade.get_process_view(task.application_id)
    now = request.app.state.clock.now()
    return TaskDetailOut(
        task=TaskOut(
            **{k: v for k, v in asdict(task).items() if k != "node_id"},
            overdue=task.status in ("open", "in_progress")
            and task.due_at is not None
            and now > task.due_at,
        ),
        process=ProcessOut.model_validate(asdict(view)) if view else None,
    )


@router.post("/tasks/{task_id}/claim", response_model=TaskOut, dependencies=CanUpdate)
async def claim_task(
    task_id: UUID, request: Request, user_id: CurrentUserId, service: Service, session: DbSession
) -> TaskOut:
    task = await service.claim(task_id, user_id)
    await commit(session)
    return task_out(request, task)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut, dependencies=CanUpdate)
async def complete_task(
    task_id: UUID,
    data: TaskResultIn,
    request: Request,
    user_id: CurrentUserId,
    service: Service,
    session: DbSession,
) -> TaskOut:
    """Only the assignee closes the task; the process moves on in the same transaction."""
    task = await service.complete_task(task_id, user_id, data.as_result())
    await commit(session)
    return task_out(request, task)


@router.get("/processes/{application_id}", response_model=ProcessOut, dependencies=CanRead)
async def get_process(application_id: UUID, session: DbSession) -> ProcessOut:
    process = await SqlAlchemyProcessRepository(session).get_by_application(application_id)
    if process is None:
        raise NotFoundError("Process not found")
    return ProcessOut.model_validate(asdict(process_view(process)))


@router.get("/workflows", response_model=list[WorkflowOut], dependencies=CanRead)
async def list_workflows(request: Request) -> list[WorkflowOut]:
    return [
        WorkflowOut(
            code=w.definition.code,
            version=w.definition.version,
            source_hash=w.definition.source_hash,
            nodes=len(w.definition.nodes),
            flows=len(w.definition.edges),
        )
        for w in request.app.state.workflows.all()
    ]


@router.get("/workflows/{code}/diagram", dependencies=CanRead)
async def workflow_diagram(code: str, request: Request) -> Response:
    """BPMN XML for bpmn-js; highlight `visited_node_ids` from /processes."""
    catalog = request.app.state.workflows
    if code not in catalog.codes():
        raise NotFoundError("Workflow not found")
    return Response(content=catalog.source(code), media_type="application/xml")
