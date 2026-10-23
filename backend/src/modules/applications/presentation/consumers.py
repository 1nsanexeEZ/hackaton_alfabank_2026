"""Kafka entry points of the module: commands of the process engine and the
stage labels from its events."""

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.process import StepCompleted
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.applications.presentation.dependencies import (
    handle_command_use_case,
    set_client_stage_use_case,
)

MODULE = "applications"


async def handle_command(ctx: HandlerContext, command: IntegrationMessage) -> None:
    await handle_command_use_case(ctx).execute(command, ctx.envelope.event_id)


async def handle_step_completed(ctx: HandlerContext, event: StepCompleted) -> None:
    """The stage label shown to the client ("Проверяем данные о компании")."""
    await set_client_stage_use_case(ctx).execute(event.application_id, event.client_stage)


def subscriptions() -> list[Subscription]:
    return [
        Subscription(MODULE, topics.APPLICATIONS_COMMANDS, "applications.commands", handle_command),
        Subscription(
            MODULE,
            topics.PROCESS_EVENTS,
            "applications.process-events",
            handle_step_completed,
            message_types=frozenset({StepCompleted.TYPE}),
        ),
    ]
