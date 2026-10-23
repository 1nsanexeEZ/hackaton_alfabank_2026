"""process.events -> the client stage of an application, tasks and failures for
the back office."""

from src.core.messaging.contracts.process import ProcessFailed, StepCompleted, UserTaskCreated
from src.modules.notifications.application.deliveries.context import (
    DeliveryContext,
    Handlers,
    bank_entry,
    client_link,
)
from src.modules.notifications.domain import templates as t
from src.modules.notifications.domain.feed import (
    UNDERWRITERS,
    Delivery,
    FeedEntry,
    Recipient,
    stage_group,
    task_group,
)


class ProcessDeliveries:
    def __init__(self, ctx: DeliveryContext) -> None:
        self._ctx = ctx

    def handlers(self) -> Handlers:
        return {
            StepCompleted: self._step_completed,
            UserTaskCreated: self._task_created,
            ProcessFailed: self._process_failed,
        }

    async def _step_completed(self, event: StepCompleted) -> list[Delivery]:
        if not event.client_stage:
            return []  # an internal step the client does not see
        app = await self._ctx.application(event.application_id)
        title, body = t.STAGE.render(stage=event.client_stage, number=app.number)
        entry = FeedEntry(
            type="stage_changed",
            audience="client",
            title=title,
            body=body,
            link=client_link(app.id),
            priority="low",
            organization_id=app.organization_id,
            application_id=app.id,
            group_key=stage_group(app.id),
        )
        return [Delivery(entry, await self._ctx.members(app.organization_id), replace_group=True)]

    async def _task_created(self, event: UserTaskCreated) -> list[Delivery]:
        app = await self._ctx.application(event.application_id)
        due = f"Срок — до {t.day(event.due_at)}." if event.due_at else ""
        rendered = t.BANK_TASK.render(
            task=t.TASK_TITLES.get(event.task_type, event.task_type),
            number=app.number,
            organization=await self._ctx.bank_name(app),
            due=due,
        )
        entry = bank_entry(
            app,
            rendered,
            "high",
            action_required=True,
            type="task_assigned",
            link=f"/backoffice/tasks/{event.task_id}",
            group_key=task_group(event.task_id),
        )
        return [Delivery(entry, (Recipient.role(event.candidate_role),))]

    async def _process_failed(self, event: ProcessFailed) -> list[Delivery]:
        app = await self._ctx.application(event.application_id)
        rendered = t.BANK_PROCESS_FAILED.render(number=app.number, reason=event.reason)
        entry = bank_entry(app, rendered, "high", action_required=True)
        return [Delivery(entry, (UNDERWRITERS,))]
