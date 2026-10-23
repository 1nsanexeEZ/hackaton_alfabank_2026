from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.process.application.service import ACTIVE_TASK_STATUSES
from src.modules.process.domain.process import ProcessInstance
from src.modules.process.domain.steps import STEPS
from src.modules.process.domain.tasks import UserTask
from src.modules.process.facade import ProcessViewDTO, StepViewDTO, UserTaskDTO
from src.modules.process.infrastructure.repository import (
    SqlAlchemyProcessRepository,
    SqlAlchemyTaskRepository,
)


def process_view(process: ProcessInstance) -> ProcessViewDTO:
    visited: list[str] = []
    for step in process.steps:
        if step.node_id not in visited:
            visited.append(step.node_id)
    return ProcessViewDTO(
        process_id=process.id,
        application_id=process.application_id,
        workflow_code=process.workflow.code,
        workflow_version=process.workflow.version,
        status=process.status.value,  # type: ignore[arg-type]
        current_node_id=None if process.is_finished else process.current_node_id,
        client_stage=process.client_stage(),
        visited_node_ids=tuple(visited),
        steps=tuple(
            StepViewDTO(
                node_id=s.node_id,
                step_code=s.step_code,
                kind=s.kind.value,  # type: ignore[arg-type]
                iteration=s.iteration,
                started_at=s.started_at,
                finished_at=s.finished_at,
                outcome=s.outcome,
                client_stage=process.workflow.node(s.node_id).config.client_stage
                or STEPS[s.step_code].client_stage,
                error=s.error,
            )
            for s in process.steps
        ),
        started_at=process.created_at,
        finished_at=process.finished_at,
    )


def task_dto(task: UserTask) -> UserTaskDTO:
    return UserTaskDTO(
        id=task.id,
        process_id=task.process_id,
        application_id=task.application_id,
        node_id=task.node_id,
        type=task.type,
        candidate_role=task.candidate_role,
        assignee_id=task.assignee_id,
        status=task.status.value,  # type: ignore[arg-type]
        form_schema=dict(task.form_schema),
        created_at=task.created_at,
        due_at=task.due_at,
        result=task.result,
        completed_by=task.completed_by,
    )


class ProcessFacadeImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._processes = SqlAlchemyProcessRepository(session)
        self._tasks = SqlAlchemyTaskRepository(session)

    async def get_process_view(self, application_id: UUID) -> ProcessViewDTO | None:
        process = await self._processes.get_by_application(application_id)
        return process_view(process) if process else None

    async def list_open_tasks(
        self, role: str, limit: int = 50, offset: int = 0
    ) -> list[UserTaskDTO]:
        tasks = await self._tasks.search(role, ACTIVE_TASK_STATUSES, limit, offset)
        return [task_dto(task) for task in tasks]

    async def get_task(self, task_id: UUID) -> UserTaskDTO | None:
        task = await self._tasks.get(task_id)
        return task_dto(task) if task else None
