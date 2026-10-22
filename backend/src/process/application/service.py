"""Use cases of the process engine.

Never commits: inside a Kafka handler the message processor commits the
process, its outgoing commands and events and the inbox mark together; the
task endpoints and the timeout job commit around these calls.
"""

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.core.messaging.contracts import process as contracts
from src.core.messaging.contracts.base import IntegrationMessage, get_contract
from src.core.messaging.outbox import OutboxWriter
from src.process.application.ports import ProcessRepository, TaskRepository, WorkflowSource
from src.process.domain.context import ProcessContext
from src.process.domain.events import (
    ProcessCompleted,
    ProcessEvent,
    ProcessFailed,
    ProcessStarted,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.process.domain.process import ProcessInstance
from src.process.domain.steps import CommandRequest, ProcessFacts, Trigger
from src.process.domain.tasks import TaskStatus, UserTask
from src.products.facade import ProductsFacade

logger = logging.getLogger(__name__)


class ProcessService:
    def __init__(
        self,
        *,
        processes: ProcessRepository,
        tasks: TaskRepository,
        outbox: OutboxWriter,
        workflows: WorkflowSource,
        facts: ProcessFacts,
        products: ProductsFacade | None,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._processes = processes
        self._tasks = tasks
        self._outbox = outbox
        self._workflows = workflows
        self._facts = facts
        self._products = products
        self._clock = clock
        self._new_id = new_id

    async def start(
        self,
        application_id: UUID,
        organization_id: UUID,
        product_code: str,
        causation_id: UUID | None,
    ) -> bool:
        """ApplicationSubmitted: one process per application, a repeat is ignored.

        No route for the product, or the application itself is gone: a retry
        cannot help, so it is logged as an error and acknowledged."""
        if await self._processes.get_by_application(application_id) is not None:
            return False
        assert self._products is not None
        now = self._clock.now()
        try:
            product = await self._products.get_product(product_code)
            workflow = self._workflows.get(product.workflow_code)
            process = ProcessInstance.start(
                id=self._new_id(),
                workflow=workflow,
                context=ProcessContext(
                    application_id=application_id,
                    organization_id=organization_id,
                    product_code=product_code,
                ),
                now=now,
            )
            await process.run(self._facts, now, self._new_id)
        except (LookupError, NotFoundError) as exc:
            logger.error("Process for application %s not started: %s", application_id, exc)
            return False
        await self._processes.add(process, self._workflows.source(workflow.code), now)
        await self._publish(process, causation_id)
        return True

    async def handle(
        self, application_id: UUID, trigger: Trigger, causation_id: UUID | None
    ) -> bool:
        """A reply, a client event or a closed task; False — not waited for."""
        process = await self._processes.get_by_application(application_id, for_update=True)
        if process is None:
            logger.info("No process for application %s, %s ignored", application_id, trigger.type)
            return False
        now = self._clock.now()
        if not await process.handle(trigger, self._facts, now, self._new_id):
            logger.info("Process of %s does not wait for %s", application_id, trigger.type)
            return False
        await self._processes.save(process, now)
        await self._publish(process, causation_id)
        return True

    async def cancel(self, application_id: UUID, causation_id: UUID | None) -> bool:
        process = await self._processes.get_by_application(application_id, for_update=True)
        if process is None or not process.cancel(self._clock.now()):
            return False
        for task in await self._tasks.active_of_process(process.id):
            task.cancel()
            await self._tasks.save(task)
        await self._processes.save(process, self._clock.now())
        await self._publish(process, causation_id)
        return True

    async def time_out(self, application_id: UUID) -> bool:
        process = await self._processes.get_by_application(application_id, for_update=True)
        if process is None:
            return False
        now = self._clock.now()
        if not await process.time_out(self._facts, now, self._new_id):
            return False
        await self._processes.save(process, now)
        await self._publish(process, None)
        return True

    # --- underwriter tasks ----------------------------------------------------

    async def claim(self, task_id: UUID, account_id: UUID) -> UserTask:
        task = await self._task(task_id)
        task.claim(account_id)
        await self._tasks.save(task)
        return task

    async def complete_task(
        self, task_id: UUID, account_id: UUID, result: dict[str, Any]
    ) -> UserTask:
        """Close the task and move the process on, in one transaction."""
        task = await self._task(task_id)
        task.complete(account_id, result, self._clock.now())
        await self._tasks.save(task)
        for event in task.pull_events():
            await self._outbox.add(
                to_contract(event), key=task.application_id, correlation_id=task.application_id
            )
        assert task.result is not None
        await self.handle(
            task.application_id,
            Trigger("UserTaskCompleted", dict(task.result), task_id=task.id),
            causation_id=None,
        )
        return task

    async def list_tasks(
        self, role: str | None, statuses: list[str], limit: int, offset: int
    ) -> list[UserTask]:
        return await self._tasks.search(role, statuses, limit, offset)

    async def _task(self, task_id: UUID) -> UserTask:
        task = await self._tasks.get(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        return task

    # --- outputs ------------------------------------------------------------

    async def _publish(self, process: ProcessInstance, causation_id: UUID | None) -> None:
        for task in process.pull_new_tasks():
            await self._tasks.add(task)
        key = process.application_id
        for event in process.pull_events():
            await self._outbox.add(
                to_contract(event), key=key, correlation_id=key, causation_id=causation_id
            )
        for command in process.pull_commands():
            await self._outbox.add(
                command_contract(command.request),
                key=key,
                correlation_id=key,
                causation_id=causation_id,
                # replies are matched by this id
                event_id=command.command_id,
            )


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


ACTIVE_TASK_STATUSES = [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]
