"""support.events -> the queue entry for the back office, the client's entry of a ticket."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.messaging.contracts.support import (
    SupportMessagePosted,
    SupportTicketOpened,
    SupportTicketStatusChanged,
)
from tests.notifications.conftest import FeedHarness, World

TICKET = uuid4()
CLIENT = uuid4()
ANNA = uuid4()


def common(world: World, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "ticket_id": TICKET,
        "number": "ТП-2026-000001",
        "subject": "Не вижу выписку",
        "client_id": CLIENT,
        "organization_id": world.romashka.id,
    }
    return values | overrides


def status(world: World, source: str, target: str, side: str, **overrides: Any) -> Any:
    return SupportTicketStatusChanged(
        **common(world, **overrides),
        from_status=source,
        to_status=target,
        side=side,
        actor_id=ANNA if side == "staff" else CLIENT,
    )


def message(world: World, side: str, **overrides: Any) -> SupportMessagePosted:
    return SupportMessagePosted(
        **common(world, **overrides),
        message_id=uuid4(),
        side=side,
        author_id=ANNA if side == "staff" else CLIENT,
        preview="Выписка на месте, обновите страницу",
    )


@pytest.fixture
def opened(world: World) -> SupportTicketOpened:
    return SupportTicketOpened(**common(world))


async def test_new_ticket_waits_for_the_back_office_until_taken(
    feed: FeedHarness, world: World, opened: SupportTicketOpened
) -> None:
    await feed.deliver(opened)

    [row] = await feed.rows()
    assert (row.recipient_type, row.recipient_id, row.audience) == ("role", "underwriter", "bank")
    assert (row.type, row.action_required) == ("support", True)
    assert row.title == "Новое обращение ТП-2026-000001"
    assert row.body == "«Не вижу выписку»\nООО «Ромашка»"
    assert row.link == f"/backoffice/support/{TICKET}"

    await feed.deliver(status(world, "open", "in_progress", "staff", assignee_id=ANNA))

    queue, client = await feed.rows()
    assert queue.action_required is False
    assert (client.recipient_id, client.audience) == (str(CLIENT), "client")
    assert client.title == "Обращение ТП-2026-000001 взято в работу"
    assert client.link == f"/support/{TICKET}"


async def test_a_ticket_without_a_company(feed: FeedHarness, world: World) -> None:
    await feed.deliver(SupportTicketOpened(**common(world, organization_id=None)))

    [row] = await feed.rows()
    assert row.body == "«Не вижу выписку»"
    assert row.organization_id is None


async def test_closed_by_the_client_before_anyone_took_it(
    feed: FeedHarness, world: World, opened: SupportTicketOpened
) -> None:
    await feed.deliver(opened)
    await feed.deliver(status(world, "open", "closed", "client"))

    [queue] = await feed.rows()
    assert queue.action_required is False


async def test_answers_of_the_employee_reach_the_client_as_one_entry(
    feed: FeedHarness, world: World
) -> None:
    await feed.deliver(message(world, "staff", assignee_id=ANNA))
    await feed.deliver(message(world, "staff", assignee_id=ANNA))

    [row] = await feed.rows(recipient_id=str(CLIENT))
    assert (row.type, row.audience) == ("support", "client")
    assert row.title == "Ответ по обращению ТП-2026-000001"
    assert row.body == "«Не вижу выписку»\nВыписка на месте, обновите страницу"

    await feed.deliver(status(world, "in_progress", "resolved", "staff", assignee_id=ANNA))
    [row] = await feed.rows(recipient_id=str(CLIENT))
    assert row.title == "Обращение ТП-2026-000001 решено"


async def test_client_message_goes_to_the_employee_who_took_it(
    feed: FeedHarness, world: World
) -> None:
    await feed.deliver(message(world, "client"))  # still in the queue
    assert await feed.rows() == []

    await feed.deliver(message(world, "client", assignee_id=ANNA))

    [row] = await feed.rows()
    assert (row.recipient_type, row.recipient_id, row.audience) == ("account", str(ANNA), "bank")
    assert row.title == "Клиент написал в обращение ТП-2026-000001"


async def test_what_the_client_did_is_not_told_back_to_them(feed: FeedHarness, world: World) -> None:
    await feed.deliver(status(world, "resolved", "in_progress", "client", assignee_id=ANNA))
    await feed.deliver(status(world, "in_progress", "closed", "client", assignee_id=ANNA))

    assert await feed.rows() == []


async def test_returned_to_the_queue(
    feed: FeedHarness, world: World, opened: SupportTicketOpened
) -> None:
    await feed.deliver(opened)
    await feed.deliver(status(world, "open", "in_progress", "staff", assignee_id=ANNA))
    await feed.deliver(status(world, "in_progress", "open", "staff"))

    [queue] = await feed.rows(recipient_type="role")
    assert queue.title == "Обращение ТП-2026-000001 вернулось в очередь"
    assert queue.action_required is True


def _ids(rows: list[Any]) -> list[UUID]:
    return [r.id for r in rows]


async def test_redelivery_writes_nothing_new(
    feed: FeedHarness, world: World, opened: SupportTicketOpened
) -> None:
    event_id = uuid4()
    await feed.deliver(opened, event_id)
    before = _ids(await feed.rows())

    assert await feed.deliver(opened, event_id) == "duplicate"

    assert _ids(await feed.rows()) == before
