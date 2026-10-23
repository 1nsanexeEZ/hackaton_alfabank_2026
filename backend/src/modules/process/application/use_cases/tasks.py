"""Underwriter tasks of the back office API: commit through the unit of work."""

from typing import Any
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.core.uow import UnitOfWork
from src.modules.process.application.dto.tasks import TaskDetailDTO, TaskDTO, TaskQueueStatus
from src.modules.process.application.interfaces.outbox import MessageOutbox
from src.modules.process.application.interfaces.repositories import (
    ProcessRepository,
    TaskRepository,
)
from src.modules.process.application.mappers.messages import to_contract
from src.modules.process.application.mappers.views import process_view, task_card
from src.modules.process.application.use_cases.processes import HandleTriggerUseCase
from src.modules.process.domain.enums import ACTIVE_TASK_STATUSES
from src.modules.process.domain.steps import Trigger
from src.modules.process.domain.tasks import UserTask


async def _task(tasks: TaskRepository, task_id: UUID) -> UserTask:
    task = await tasks.get(task_id)
    if task is None:
        raise NotFoundError("Task not found")
    return task


class ListTasksUseCase:
    def __init__(self, tasks: TaskRepository, clock: Clock) -> None:
        self._tasks = tasks
        self._clock = clock

    async def execute(
        self, role: str | None, status: TaskQueueStatus, limit: int, offset: int
    ) -> list[TaskDTO]:
        statuses = ACTIVE_TASK_STATUSES if status == "active" else [status]
        tasks = await self._tasks.search(role, statuses, limit, offset)
        return [task_card(task, self._clock.now()) for task in tasks]


class GetTaskDetailUseCase:
    """The task and the process of its application."""

    def __init__(self, tasks: TaskRepository, processes: ProcessRepository, clock: Clock) -> None:
        self._tasks = tasks
        self._processes = processes
        self._clock = clock

    async def execute(self, task_id: UUID) -> TaskDetailDTO:
        task = await _task(self._tasks, task_id)
        process = await self._processes.get_by_application(task.application_id)
        return TaskDetailDTO(
            task=task_card(task, self._clock.now()),
            process=process_view(process) if process else None,
        )


class ClaimTaskUseCase:
    def __init__(self, uow: UnitOfWork, tasks: TaskRepository, clock: Clock) -> None:
        self._uow = uow
        self._tasks = tasks
        self._clock = clock

    async def execute(self, task_id: UUID, account_id: UUID) -> TaskDTO:
        async with self._uow:
            task = await _task(self._tasks, task_id)
            task.claim(account_id)
            await self._tasks.save(task)
            await self._uow.commit()
        return task_card(task, self._clock.now())


class CompleteTaskUseCase:
    """Close the task and move the process on, in one transaction."""

    def __init__(
        self,
        uow: UnitOfWork,
        tasks: TaskRepository,
        outbox: MessageOutbox,
        clock: Clock,
        handle: HandleTriggerUseCase,
    ) -> None:
        self._uow = uow
        self._tasks = tasks
        self._outbox = outbox
        self._clock = clock
        self._handle = handle

    async def execute(self, task_id: UUID, account_id: UUID, result: dict[str, Any]) -> TaskDTO:
        async with self._uow:
            task = await _task(self._tasks, task_id)
            task.complete(account_id, result, self._clock.now())
            await self._tasks.save(task)
            for event in task.pull_events():
                await self._outbox.add(
                    to_contract(event), key=task.application_id, correlation_id=task.application_id
                )
            assert task.result is not None
            await self._handle.execute(
                task.application_id,
                Trigger("UserTaskCompleted", dict(task.result), task_id=task.id),
                causation_id=None,
            )
            await self._uow.commit()
        return task_card(task, self._clock.now())
