"""What the use cases of the engine share."""

from uuid import UUID

from src.modules.process.application.interfaces.outbox import MessageOutbox
from src.modules.process.application.interfaces.repositories import TaskRepository
from src.modules.process.application.mappers.messages import command_contract, to_contract
from src.modules.process.domain.process import ProcessInstance


async def publish(
    process: ProcessInstance,
    tasks: TaskRepository,
    outbox: MessageOutbox,
    causation_id: UUID | None,
) -> None:
    """What a run of the process left: new tasks into the repository, events
    and commands into the outbox of the same transaction."""
    for task in process.pull_new_tasks():
        await tasks.add(task)
    key = process.application_id
    for event in process.pull_events():
        await outbox.add(to_contract(event), key=key, correlation_id=key, causation_id=causation_id)
    for command in process.pull_commands():
        await outbox.add(
            command_contract(command.request),
            key=key,
            correlation_id=key,
            causation_id=causation_id,
            # replies are matched by this id
            event_id=command.command_id,
        )
