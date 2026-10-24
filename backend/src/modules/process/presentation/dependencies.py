"""Use cases for the routers, the Kafka handlers, the timeout job and the
facade: adapters are picked here, use cases see only interfaces."""

from functools import partial
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry, use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.subscriber import HandlerContext
from src.core.uow import UnitOfWork
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.process.application.interfaces.outbox import MessageOutbox
from src.modules.process.application.interfaces.repositories import (
    ProcessRepository,
    TaskRepository,
)
from src.modules.process.application.interfaces.workflows import WorkflowSource
from src.modules.process.application.mappers.messages import PRODUCER
from src.modules.process.application.use_cases.processes import (
    CancelProcessUseCase,
    HandleTriggerUseCase,
    StartProcessUseCase,
)
from src.modules.process.application.use_cases.tasks import (
    ClaimTaskUseCase,
    CompleteTaskUseCase,
    GetTaskDetailUseCase,
    ListTasksUseCase,
)
from src.modules.process.application.use_cases.timeouts import TimeOutStuckStepsUseCase
from src.modules.process.application.use_cases.views import (
    GetProcessUseCase,
    GetProcessViewUseCase,
    GetTaskUseCase,
    ListOpenTasksUseCase,
)
from src.modules.process.application.use_cases.workflows import (
    GetWorkflowDiagramUseCase,
    ListWorkflowsUseCase,
)
from src.modules.process.domain.steps import ProcessFacts
from src.modules.process.infrastructure.adapters.application_facts import ApplicationFacts
from src.modules.process.infrastructure.adapters.process_facade import ProcessFacadeImpl
from src.modules.process.infrastructure.adapters.process_transaction import (
    SqlAlchemyProcessTransaction,
)
from src.modules.process.infrastructure.adapters.task_unit_of_work import TaskUnitOfWork
from src.modules.process.infrastructure.repositories.processes import (
    SqlAlchemyProcessRepository,
)
from src.modules.process.infrastructure.repositories.tasks import SqlAlchemyTaskRepository
from src.modules.products.facade import ProductsFacade

# --- facade --------------------------------------------------------------------


def process_facade(session: AsyncSession, workflows: WorkflowSource) -> ProcessFacadeImpl:
    processes = SqlAlchemyProcessRepository(session)
    tasks = SqlAlchemyTaskRepository(session)
    return ProcessFacadeImpl(
        GetProcessViewUseCase(processes),
        ListOpenTasksUseCase(tasks),
        GetTaskUseCase(tasks),
        ListWorkflowsUseCase(workflows),
    )


# --- Kafka: the handler's transaction is committed by the core with the inbox ---


def _handler_facts(ctx: HandlerContext) -> ApplicationFacts:
    return ApplicationFacts(
        ctx.facade(ApplicationsFacade), ctx.facade(ClientsFacade), ctx.facade(IdentityFacade)
    )


def start_process_use_case(ctx: HandlerContext) -> StartProcessUseCase:
    return StartProcessUseCase(
        SqlAlchemyProcessRepository(ctx.session),
        SqlAlchemyTaskRepository(ctx.session),
        ctx.outbox,
        ctx.facade(WorkflowSource),  # registered by process.module.wire
        _handler_facts(ctx),
        ctx.facade(ProductsFacade),
        ctx.clock,
    )


def handle_trigger_use_case(ctx: HandlerContext) -> HandleTriggerUseCase:
    return HandleTriggerUseCase(
        SqlAlchemyProcessRepository(ctx.session),
        SqlAlchemyTaskRepository(ctx.session),
        ctx.outbox,
        _handler_facts(ctx),
        ctx.clock,
    )


def cancel_process_use_case(ctx: HandlerContext) -> CancelProcessUseCase:
    return CancelProcessUseCase(
        SqlAlchemyProcessRepository(ctx.session),
        SqlAlchemyTaskRepository(ctx.session),
        ctx.outbox,
        ctx.clock,
    )


# --- the timeout job: a transaction of its own per application -----------------


def time_out_stuck_steps_use_case(
    session_factory: async_sessionmaker[AsyncSession], facades: FacadeRegistry, clock: Clock
) -> TimeOutStuckStepsUseCase:
    transactions = partial(SqlAlchemyProcessTransaction, session_factory, facades, clock)
    return TimeOutStuckStepsUseCase(transactions, clock)


# --- adapters for the routers --------------------------------------------------

CanRead = [Depends(require_permissions(Permissions.TASKS_READ))]
CanUpdate = [Depends(require_permissions(Permissions.TASKS_UPDATE))]


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_uow(session: DbSession) -> UnitOfWork:
    return TaskUnitOfWork(session)


def get_process_repository(session: DbSession) -> ProcessRepository:
    return SqlAlchemyProcessRepository(session)


def get_task_repository(session: DbSession) -> TaskRepository:
    return SqlAlchemyTaskRepository(session)


def get_outbox(request: Request, session: DbSession) -> MessageOutbox:
    return SqlAlchemyOutboxWriter(session, PRODUCER, request.app.state.clock)


def get_workflows(request: Request) -> WorkflowSource:
    return request.app.state.workflows


def get_facts(
    applications: Annotated[ApplicationsFacade, Depends(use_facade(ApplicationsFacade))],
    clients: Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))],
    identity: Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))],
) -> ProcessFacts:
    return ApplicationFacts(applications, clients, identity)


ClockDep = Annotated[Clock, Depends(get_clock)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Processes = Annotated[ProcessRepository, Depends(get_process_repository)]
Tasks = Annotated[TaskRepository, Depends(get_task_repository)]
Outbox = Annotated[MessageOutbox, Depends(get_outbox)]
Workflows = Annotated[WorkflowSource, Depends(get_workflows)]
Facts = Annotated[ProcessFacts, Depends(get_facts)]


# --- tasks ---------------------------------------------------------------------


def get_list_tasks(tasks: Tasks, clock: ClockDep) -> ListTasksUseCase:
    return ListTasksUseCase(tasks, clock)


def get_task_detail(tasks: Tasks, processes: Processes, clock: ClockDep) -> GetTaskDetailUseCase:
    return GetTaskDetailUseCase(tasks, processes, clock)


def get_claim_task(uow: Uow, tasks: Tasks, clock: ClockDep) -> ClaimTaskUseCase:
    return ClaimTaskUseCase(uow, tasks, clock)


def get_complete_task(
    uow: Uow,
    processes: Processes,
    tasks: Tasks,
    outbox: Outbox,
    facts: Facts,
    clock: ClockDep,
) -> CompleteTaskUseCase:
    handle = HandleTriggerUseCase(processes, tasks, outbox, facts, clock)
    return CompleteTaskUseCase(uow, tasks, outbox, clock, handle)


# --- processes and routes ------------------------------------------------------


def get_get_process(processes: Processes) -> GetProcessUseCase:
    return GetProcessUseCase(processes)


def get_list_workflows(workflows: Workflows) -> ListWorkflowsUseCase:
    return ListWorkflowsUseCase(workflows)


def get_workflow_diagram(workflows: Workflows) -> GetWorkflowDiagramUseCase:
    return GetWorkflowDiagramUseCase(workflows)


ListTasksDep = Annotated[ListTasksUseCase, Depends(get_list_tasks)]
GetTaskDetailDep = Annotated[GetTaskDetailUseCase, Depends(get_task_detail)]
ClaimTaskDep = Annotated[ClaimTaskUseCase, Depends(get_claim_task)]
CompleteTaskDep = Annotated[CompleteTaskUseCase, Depends(get_complete_task)]
GetProcessDep = Annotated[GetProcessUseCase, Depends(get_get_process)]
ListWorkflowsDep = Annotated[ListWorkflowsUseCase, Depends(get_list_workflows)]
WorkflowDiagramDep = Annotated[GetWorkflowDiagramUseCase, Depends(get_workflow_diagram)]
