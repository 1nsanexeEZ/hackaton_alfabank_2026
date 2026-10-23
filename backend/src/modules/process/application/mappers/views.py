"""Process and tasks -> DTO of the facade and of the back office API."""

from datetime import datetime

from src.modules.process.application.dto.processes import ProcessViewDTO, StepViewDTO
from src.modules.process.application.dto.tasks import TaskDTO, UserTaskDTO
from src.modules.process.domain.process import ProcessInstance
from src.modules.process.domain.steps import STEPS
from src.modules.process.domain.tasks import UserTask


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


def task_card(task: UserTask, now: datetime) -> TaskDTO:
    return TaskDTO(
        id=task.id,
        process_id=task.process_id,
        application_id=task.application_id,
        type=task.type,
        candidate_role=task.candidate_role,
        status=task.status.value,  # type: ignore[arg-type]
        assignee_id=task.assignee_id,
        form_schema=task.form_schema,
        created_at=task.created_at,
        due_at=task.due_at,
        overdue=task.is_overdue(now),
        result=task.result,
        completed_by=task.completed_by,
    )
