from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from src.core.access.dependencies import CurrentUserId
from src.modules.process.application.dto.tasks import TaskQueueStatus
from src.modules.process.presentation.dependencies import (
    CanRead,
    CanUpdate,
    ClaimTaskDep,
    CompleteTaskDep,
    GetTaskDetailDep,
    ListTasksDep,
)
from src.modules.process.presentation.schemas.tasks import TaskDetailOut, TaskOut, TaskResultIn

router = APIRouter(tags=["process"])


@router.get("/tasks", response_model=list[TaskOut], dependencies=CanRead)
async def list_tasks(
    use_case: ListTasksDep,
    role: str | None = "underwriter",
    status: TaskQueueStatus = "active",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskOut]:
    """Underwriter queue by due date (the back office screen reads the projector)."""
    tasks = await use_case.execute(role, status, limit, offset)
    return [TaskOut.model_validate(task) for task in tasks]


@router.get("/tasks/{task_id}", response_model=TaskDetailOut, dependencies=CanRead)
async def get_task(task_id: UUID, use_case: GetTaskDetailDep) -> TaskDetailOut:
    return TaskDetailOut.model_validate(await use_case.execute(task_id))


@router.post("/tasks/{task_id}/claim", response_model=TaskOut, dependencies=CanUpdate)
async def claim_task(task_id: UUID, user_id: CurrentUserId, use_case: ClaimTaskDep) -> TaskOut:
    return TaskOut.model_validate(await use_case.execute(task_id, user_id))


@router.post("/tasks/{task_id}/complete", response_model=TaskOut, dependencies=CanUpdate)
async def complete_task(
    task_id: UUID, data: TaskResultIn, user_id: CurrentUserId, use_case: CompleteTaskDep
) -> TaskOut:
    """Only the assignee closes the task; the process moves on in the same transaction."""
    return TaskOut.model_validate(await use_case.execute(task_id, user_id, data.as_result()))
