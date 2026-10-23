"""The engine: start, move, cancel and time out a process.

Never commits: inside a Kafka handler the message processor commits the
process, its outgoing commands and events and the inbox mark together; the
task endpoints and the timeout job commit around these calls.
"""

import logging
from collections.abc import Callable
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.modules.process.application.interfaces.outbox import MessageOutbox
from src.modules.process.application.interfaces.repositories import (
    ProcessRepository,
    TaskRepository,
)
from src.modules.process.application.interfaces.workflows import WorkflowSource
from src.modules.process.application.use_cases.common import publish
from src.modules.process.domain.context import ProcessContext
from src.modules.process.domain.process import ProcessInstance
from src.modules.process.domain.steps import ProcessFacts, Trigger
from src.modules.products.facade import ProductsFacade

logger = logging.getLogger(__name__)


class StartProcessUseCase:
    def __init__(
        self,
        processes: ProcessRepository,
        tasks: TaskRepository,
        outbox: MessageOutbox,
        workflows: WorkflowSource,
        facts: ProcessFacts,
        products: ProductsFacade,
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

    async def execute(
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
        await publish(process, self._tasks, self._outbox, causation_id)
        return True


class HandleTriggerUseCase:
    def __init__(
        self,
        processes: ProcessRepository,
        tasks: TaskRepository,
        outbox: MessageOutbox,
        facts: ProcessFacts,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._processes = processes
        self._tasks = tasks
        self._outbox = outbox
        self._facts = facts
        self._clock = clock
        self._new_id = new_id

    async def execute(
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
        await publish(process, self._tasks, self._outbox, causation_id)
        return True


class CancelProcessUseCase:
    def __init__(
        self,
        processes: ProcessRepository,
        tasks: TaskRepository,
        outbox: MessageOutbox,
        clock: Clock,
    ) -> None:
        self._processes = processes
        self._tasks = tasks
        self._outbox = outbox
        self._clock = clock

    async def execute(self, application_id: UUID, causation_id: UUID | None) -> bool:
        process = await self._processes.get_by_application(application_id, for_update=True)
        if process is None or not process.cancel(self._clock.now()):
            return False
        for task in await self._tasks.active_of_process(process.id):
            task.cancel()
            await self._tasks.save(task)
        await self._processes.save(process, self._clock.now())
        await publish(process, self._tasks, self._outbox, causation_id)
        return True


class TimeOutProcessUseCase:
    def __init__(
        self,
        processes: ProcessRepository,
        tasks: TaskRepository,
        outbox: MessageOutbox,
        facts: ProcessFacts,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._processes = processes
        self._tasks = tasks
        self._outbox = outbox
        self._facts = facts
        self._clock = clock
        self._new_id = new_id

    async def execute(self, application_id: UUID) -> bool:
        process = await self._processes.get_by_application(application_id, for_update=True)
        if process is None:
            return False
        now = self._clock.now()
        if not await process.time_out(self._facts, now, self._new_id):
            return False
        await self._processes.save(process, now)
        await publish(process, self._tasks, self._outbox, None)
        return True
