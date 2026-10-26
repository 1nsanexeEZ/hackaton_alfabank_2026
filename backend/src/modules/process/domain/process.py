"""ProcessInstance — one run of a route for one application.

`run` walks the graph: immediate steps one after another, gateways by their
conditions, until an async step sends a command (and waits for the reply to
exactly that command), a stoppable step waits for a person, or an end event.

`handle` applies a trigger only if the process waits for exactly it: a reply
must carry `causation_id` == the id of the command sent; a task — its id. A
duplicate or a late reply from an earlier iteration of a loop is ignored.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Self
from uuid import UUID, uuid4

from src.modules.process.domain.context import ProcessContext
from src.modules.process.domain.enums import NodeType, OnFailure, ProcessStatus, StepKind, WaitKind
from src.modules.process.domain.events import (
    ProcessCompleted,
    ProcessEvent,
    ProcessFailed,
    ProcessStarted,
    StepCompleted,
    UserTaskCreated,
)
from src.modules.process.domain.steps import (
    STEPS,
    CommandRequest,
    ProcessFacts,
    StepInput,
    StepResult,
    StepSpec,
    Trigger,
)
from src.modules.process.domain.tasks import UserTask
from src.modules.process.domain.workflow import Node, WorkflowDefinition

# A route without waits that loops forever is a bug; stop instead of hanging.
MAX_TRANSITIONS_PER_RUN = 200
MANUAL_REVIEW_STEP = "underwriter_review"

IdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class WaitToken:
    kind: WaitKind
    node_id: str
    expected_types: frozenset[str]
    since: datetime
    command_event_id: UUID | None = None
    task_id: UUID | None = None

    def matches(self, trigger: Trigger) -> bool:
        if trigger.type not in self.expected_types:
            return False
        if self.kind is WaitKind.COMMAND_REPLY:
            return (
                trigger.causation_id is not None and trigger.causation_id == self.command_event_id
            )
        if self.kind is WaitKind.USER_TASK:
            return trigger.task_id is not None and trigger.task_id == self.task_id
        return True


@dataclass
class StepExecution:
    id: UUID
    node_id: str
    step_code: str
    kind: StepKind
    iteration: int
    started_at: datetime
    finished_at: datetime | None = None
    outcome: str | None = None  # completed | failed | cancelled
    command_event_id: UUID | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class OutgoingCommand:
    """A command for the outbox; its id becomes the envelope event_id, so the
    reply's causation_id can be matched."""

    command_id: UUID
    request: CommandRequest


@dataclass
class ProcessInstance:
    id: UUID
    application_id: UUID
    workflow: WorkflowDefinition
    context: ProcessContext
    current_node_id: str
    created_at: datetime
    status: ProcessStatus = ProcessStatus.RUNNING
    waiting: WaitToken | None = None
    iterations: dict[str, int] = field(default_factory=dict)
    steps: list[StepExecution] = field(default_factory=list)
    finished_at: datetime | None = None
    version: int = 1
    _events: list[ProcessEvent] = field(default_factory=list, repr=False)
    _commands: list[OutgoingCommand] = field(default_factory=list, repr=False)
    _new_tasks: list[UserTask] = field(default_factory=list, repr=False)
    _completed_in_run: list[StepExecution] = field(default_factory=list, repr=False)
    # ProcessCompleted / ProcessFailed go after the StepCompleted of the same run.
    _terminal: ProcessEvent | None = field(default=None, repr=False)

    @classmethod
    def start(
        cls,
        *,
        id: UUID,
        workflow: WorkflowDefinition,
        context: ProcessContext,
        now: datetime,
    ) -> Self:
        process = cls(
            id=id,
            application_id=context.application_id,
            workflow=workflow,
            context=context,
            current_node_id=workflow.start_node.id,
            created_at=now,
        )
        process._events.append(
            ProcessStarted(
                occurred_at=now,
                process_id=id,
                application_id=context.application_id,
                workflow_code=workflow.code,
            )
        )
        return process

    # --- reading ------------------------------------------------------------

    @property
    def is_finished(self) -> bool:
        return self.status in (
            ProcessStatus.COMPLETED,
            ProcessStatus.FAILED,
            ProcessStatus.CANCELLED,
        )

    @property
    def current_node(self) -> Node:
        return self.workflow.node(self.current_node_id)

    def client_stage(self) -> str | None:
        """What the client should see now."""
        node = self.current_node
        if node.step_code and not self.is_finished:
            return node.config.client_stage or STEPS[node.step_code].client_stage
        return self.context.last_client_stage

    def pull_events(self) -> list[ProcessEvent]:
        events, self._events = self._events, []
        return events

    def pull_commands(self) -> list[OutgoingCommand]:
        commands, self._commands = self._commands, []
        return commands

    def pull_new_tasks(self) -> list[UserTask]:
        tasks, self._new_tasks = self._new_tasks, []
        return tasks

    # --- driving ------------------------------------------------------------

    async def run(self, facts: ProcessFacts, now: datetime, new_id: IdFactory = uuid4) -> None:
        """Walk from the current node until a wait or the end."""
        if self.is_finished or self.waiting is not None:
            return
        self.status = ProcessStatus.RUNNING
        await self._walk(facts, now, new_id)

    async def handle(
        self, trigger: Trigger, facts: ProcessFacts, now: datetime, new_id: IdFactory = uuid4
    ) -> bool:
        """Apply a trigger; False — not what the process waits for (ignored)."""
        if self.is_finished or self.waiting is None or not self.waiting.matches(trigger):
            return False
        node = self.current_node
        spec = STEPS[node.step_code or ""]
        assert spec.on_reply is not None
        result = spec.on_reply(self._input(node, now, facts), trigger)
        self.waiting = None
        self.status = ProcessStatus.RUNNING
        execution = self._open_execution(node)
        if result.status == "failed":
            await self._fail_step(node, execution, result.error or "failed", facts, now, new_id)
            return True
        self.context.update(dict(result.updates))
        self._finish_execution(execution, now, "completed")
        self._move_along(node)
        await self._walk(facts, now, new_id)
        return True

    async def time_out(self, facts: ProcessFacts, now: datetime, new_id: IdFactory = uuid4) -> bool:
        """A module did not answer within the node's timeout: the step fails and
        `on_failure` decides (usually an underwriter takes over)."""
        token = self.waiting
        if self.is_finished or token is None or token.kind is not WaitKind.COMMAND_REPLY:
            return False
        node = self.current_node
        timeout = node.config.timeout_seconds
        if timeout is None or now < token.since + timedelta(seconds=timeout):
            return False
        self.waiting = None
        self.status = ProcessStatus.RUNNING
        execution = self._open_execution(node)
        await self._fail_step(
            node, execution, f"{node.step_code}: no reply in {timeout} s", facts, now, new_id
        )
        return True

    def cancel(self, now: datetime) -> bool:
        """The client cancelled the application: stop waiting, close tasks."""
        if self.is_finished:
            return False
        execution = self._open_execution(self.current_node) if self.waiting else None
        if execution is not None:
            self._finish_execution(execution, now, "cancelled")
        self.waiting = None
        self.status = ProcessStatus.CANCELLED
        self.finished_at = now
        self._events.append(
            ProcessCompleted(
                occurred_at=now,
                process_id=self.id,
                application_id=self.application_id,
                outcome="CANCELLED",
            )
        )
        return True

    # --- internals ----------------------------------------------------------

    async def _walk(self, facts: ProcessFacts, now: datetime, new_id: IdFactory) -> None:
        for _ in range(MAX_TRANSITIONS_PER_RUN):
            node = self.current_node
            if node.type is NodeType.START:
                self._move_along(node)
            elif node.type is NodeType.GATEWAY:
                self._choose(node)
            elif node.type is NodeType.END:
                self._complete(node, now)
                break
            else:
                if not await self._execute(node, facts, now, new_id):
                    break
        else:
            self._mark_failed(now, f"no wait or end after {MAX_TRANSITIONS_PER_RUN} transitions")
        self._announce_stage(now)

    async def _execute(
        self, node: Node, facts: ProcessFacts, now: datetime, new_id: IdFactory
    ) -> bool:
        """Run one task node; True — the walk goes on."""
        count = self.iterations.get(node.id, 0) + 1
        self.iterations[node.id] = count
        limit = node.config.max_iterations
        # The underwriter's review is the way out of every loop: a person decides each round,
        # so it is never cut by the limit (a rejected manual decision opens a new task).
        if limit is not None and count > limit and node.step_code != MANUAL_REVIEW_STEP:
            return self._escalate(
                node,
                f"Этап «{_stage(node)}» повторился больше {limit} раз — нужно решение специалиста",
                now,
            )

        spec = STEPS[node.step_code or ""]
        execution = StepExecution(
            id=new_id(),
            node_id=node.id,
            step_code=spec.code,
            kind=spec.kind,
            iteration=count,
            started_at=now,
        )
        self.steps.append(execution)
        result = await spec.run(self._input(node, now, facts))

        if result.status == "failed":
            return await self._fail_step(
                node, execution, result.error or "failed", facts, now, new_id, walk=False
            )
        self.context.update(dict(result.updates))
        sent = self._send(result, new_id)
        if result.status == "completed":
            self._finish_execution(execution, now, "completed")
            self._move_along(node)
            return True
        self._wait(node, spec, result, execution, sent, now, new_id)
        return False

    def _send(self, result: StepResult, new_id: IdFactory) -> list[OutgoingCommand]:
        sent = [OutgoingCommand(new_id(), request) for request in result.commands]
        self._commands.extend(sent)
        return sent

    def _wait(
        self,
        node: Node,
        spec: StepSpec,
        result: StepResult,
        execution: StepExecution,
        sent: list[OutgoingCommand],
        now: datetime,
        new_id: IdFactory,
    ) -> None:
        self.status = ProcessStatus.WAITING
        if result.task is not None:
            task = UserTask(
                id=new_id(),
                process_id=self.id,
                application_id=self.application_id,
                node_id=node.id,
                type=result.task.task_type,
                candidate_role=result.task.candidate_role,
                form_schema=dict(result.task.form_schema),
                created_at=now,
                due_at=result.task.due_at,
                reason=result.task.reason,
            )
            self._new_tasks.append(task)
            self.context.last_task_id = task.id
            self.waiting = WaitToken(
                WaitKind.USER_TASK, node.id, result.expects, now, task_id=task.id
            )
            self._events.append(
                UserTaskCreated(
                    occurred_at=now,
                    process_id=self.id,
                    application_id=self.application_id,
                    task_id=task.id,
                    task_type=task.type,
                    candidate_role=task.candidate_role,
                    due_at=task.due_at,
                )
            )
        elif spec.kind is StepKind.ASYNC:
            command_id = sent[0].command_id
            execution.command_event_id = command_id
            self.waiting = WaitToken(
                WaitKind.COMMAND_REPLY, node.id, result.expects, now, command_event_id=command_id
            )
        else:
            self.waiting = WaitToken(WaitKind.CLIENT_EVENT, node.id, result.expects, now)

    async def _fail_step(
        self,
        node: Node,
        execution: StepExecution,
        error: str,
        facts: ProcessFacts,
        now: datetime,
        new_id: IdFactory,
        walk: bool = True,
    ) -> bool:
        execution.error = error
        self._finish_execution(execution, now, "failed")
        if node.config.on_failure is OnFailure.MANUAL_REVIEW:
            escalated = self._escalate(node, f"Сбой на этапе «{_stage(node)}» ({error})", now)
            if escalated and walk:
                await self._walk(facts, now, new_id)
            return escalated
        self._mark_failed(now, error)
        if walk:
            self._announce_stage(now)
        return False

    def _escalate(self, node: Node, reason: str, now: datetime) -> bool:
        """Hand the application to an underwriter; True — the walk goes on."""
        target = self.workflow.first_node_with_step(MANUAL_REVIEW_STEP)
        if target is None or target.id == node.id:
            self._mark_failed(now, reason)
            return False
        self.context.manual_review_reason = reason
        self.current_node_id = target.id
        return True

    def _choose(self, gateway: Node) -> None:
        values = self.context.as_mapping()
        edges = self.workflow.outgoing(gateway.id)
        chosen = next(
            (
                e
                for e in edges
                if not e.is_default and e.condition is not None and e.condition(values)
            ),
            None,
        ) or next(e for e in edges if e.is_default)
        self.current_node_id = chosen.target

    def _move_along(self, node: Node) -> None:
        [edge] = self.workflow.outgoing(node.id)
        self.current_node_id = edge.target

    def _complete(self, end: Node, now: datetime) -> None:
        self.status = ProcessStatus.COMPLETED
        self.finished_at = now
        self._terminal = ProcessCompleted(
            occurred_at=now,
            process_id=self.id,
            application_id=self.application_id,
            outcome=end.name or end.id,
        )

    def _mark_failed(self, now: datetime, reason: str) -> None:
        self.status = ProcessStatus.FAILED
        self.waiting = None
        self.finished_at = now
        self._terminal = ProcessFailed(
            occurred_at=now,
            process_id=self.id,
            application_id=self.application_id,
            reason=reason,
        )

    def _open_execution(self, node: Node) -> StepExecution:
        for execution in reversed(self.steps):
            if execution.node_id == node.id and execution.finished_at is None:
                return execution
        raise RuntimeError(f"No running step at {node.id}")

    def _finish_execution(self, execution: StepExecution, now: datetime, outcome: str) -> None:
        execution.finished_at = now
        execution.outcome = outcome
        if outcome == "completed":
            self._completed_in_run.append(execution)

    def _announce_stage(self, now: datetime) -> None:
        """StepCompleted for every step finished in this run; the last one
        carries the new client stage if it changed."""
        completed, self._completed_in_run = self._completed_in_run, []
        stage = self.client_stage() if self.status is not ProcessStatus.FAILED else None
        if not self.is_finished and self.waiting is None:
            stage = None
        if self.status is ProcessStatus.COMPLETED and completed:
            last = STEPS[completed[-1].step_code]
            node = self.workflow.node(completed[-1].node_id)
            stage = node.config.client_stage or last.client_stage
        changed = stage is not None and stage != self.context.last_client_stage
        for index, execution in enumerate(completed):
            is_last = index == len(completed) - 1
            self._events.append(
                StepCompleted(
                    occurred_at=now,
                    process_id=self.id,
                    application_id=self.application_id,
                    node_id=execution.node_id,
                    step_code=execution.step_code,
                    client_stage=stage if is_last and changed else None,
                )
            )
        if changed and completed:
            self.context.last_client_stage = stage
        if self._terminal is not None:
            self._events.append(self._terminal)
            self._terminal = None

    def _input(self, node: Node, now: datetime, facts: ProcessFacts) -> StepInput:
        return StepInput(context=self.context, node=node, now=now, facts=facts)


def _stage(node: Node) -> str:
    """The step as the underwriter reads it: its client stage, the code if it has none."""
    if node.config.client_stage:
        return node.config.client_stage
    spec = STEPS.get(node.step_code or "")
    return spec.client_stage if spec is not None else node.step_code or node.id
