"""The staff side of support: the queue, take, answer, resolve, close, rights."""

import pytest

from tests.support.api.conftest import World


def test_staff_sees_the_tickets_of_every_client(world: World) -> None:
    romashka = world.open(world.director)
    vector = world.open(world.petrov)

    queue = world.client.get("/support/queue", headers=world.as_staff(world.anna))

    assert queue.status_code == 200
    assert {t["id"] for t in queue.json()} == {romashka["id"], vector["id"]}
    card = world.client.get(f"/support/queue/{vector['id']}", headers=world.as_staff(world.anna))
    assert card.status_code == 200
    assert card.json()["author_name"] == "Пётр Петров"


def test_queue_filters(world: World) -> None:
    free = world.open()
    annas = world.take(world.open())
    boriss = world.take(world.open(), world.boris)
    closed = world.open()
    world.client.post(
        f"/support/tickets/{closed['id']}/close", headers=world.as_client(world.director)
    )

    def ids(**params: object) -> set[str]:
        response = world.client.get(
            "/support/queue", params=params, headers=world.as_staff(world.anna)
        )
        assert response.status_code == 200, response.text
        return {t["id"] for t in response.json()}

    assert ids(scope="unassigned") == {free["id"], closed["id"]}
    assert ids(scope="unassigned", status="open") == {free["id"]}
    assert ids(scope="mine") == {annas["id"]}
    assert ids(status="in_progress") == {annas["id"], boriss["id"]}
    assert ids(status="closed") == {closed["id"]}
    assert len(ids()) == 4
    assert ids(limit=1, offset=0) | ids(limit=1, offset=1) <= ids()


def test_take_makes_the_ticket_the_callers(world: World) -> None:
    ticket = world.open()

    taken = world.take(ticket, world.anna)

    assert taken["status"] == "in_progress"
    assert taken["assignee_id"] == str(world.anna)
    assert taken["assignee_name"] == "Анна Аналитикова"
    assert taken["taken_at"] is not None
    assert world.outbox_types() == ["SupportTicketOpened", "SupportTicketStatusChanged"]


@pytest.mark.parametrize("second", ["anna", "boris"])
def test_take_twice_is_409(world: World, second: str) -> None:
    ticket = world.take(world.open(), world.anna)

    again = world.client.post(
        f"/support/queue/{ticket['id']}/take", headers=world.as_staff(getattr(world, second))
    )

    assert again.status_code == 409
    assert again.json()["details"] == {"code": "already_taken", "assignee_id": str(world.anna)}


def test_only_the_one_who_took_it_answers(world: World) -> None:
    ticket = world.open()
    answer = {"text": "Выписка на месте, обновите страницу"}

    early = world.client.post(
        f"/support/queue/{ticket['id']}/messages", json=answer, headers=world.as_staff(world.anna)
    )
    assert early.status_code == 409
    assert early.json()["details"]["code"] == "not_taken"

    world.take(ticket, world.anna)
    stranger = world.client.post(
        f"/support/queue/{ticket['id']}/messages", json=answer, headers=world.as_staff(world.boris)
    )
    assert stranger.status_code == 403
    assert stranger.json()["details"]["code"] == "not_assignee"

    reply = world.client.post(
        f"/support/queue/{ticket['id']}/messages", json=answer, headers=world.as_staff(world.anna)
    )
    assert reply.status_code == 201, reply.text
    body = reply.json()
    assert body["last_message_side"] == "staff"
    assert body["messages"][-1]["author_name"] == "Анна Аналитикова"
    assert world.outbox_types()[-1] == "SupportMessagePosted"


def test_the_whole_conversation(world: World) -> None:
    ticket = world.take(world.open())
    staff, client = world.as_staff(world.anna), world.as_client(world.director)
    base = f"/support/queue/{ticket['id']}"

    world.client.post(f"{base}/messages", json={"text": "Уточните ИНН"}, headers=staff)
    resolved = world.client.post(f"{base}/resolve", headers=staff)
    assert resolved.json()["status"] == "resolved"

    reopened = world.client.post(
        f"/support/tickets/{ticket['id']}/messages", json={"text": "Не помогло"}, headers=client
    )
    assert reopened.json()["status"] == "in_progress"
    assert reopened.json()["assignee_id"] == str(world.anna)

    closed = world.client.post(f"{base}/close", headers=staff)
    assert closed.json()["status"] == "closed"
    after = world.client.post(f"{base}/messages", json={"text": "Ещё"}, headers=staff)
    assert after.status_code == 409
    assert after.json()["details"]["code"] == "ticket_closed"
    assert [m["side"] for m in closed.json()["messages"]] == ["client", "staff", "client"]


def test_release_returns_the_ticket_to_the_queue(world: World) -> None:
    ticket = world.take(world.open(), world.anna)

    stranger = world.client.post(
        f"/support/queue/{ticket['id']}/release", headers=world.as_staff(world.boris)
    )
    assert stranger.status_code == 403
    released = world.client.post(
        f"/support/queue/{ticket['id']}/release", headers=world.as_staff(world.anna)
    )
    assert released.status_code == 200
    assert (released.json()["status"], released.json()["assignee_id"]) == ("open", None)

    assert world.take(ticket, world.boris)["assignee_id"] == str(world.boris)


def test_another_employee_does_not_resolve_or_close(world: World) -> None:
    ticket = world.take(world.open(), world.anna)

    for action in ("resolve", "close"):
        response = world.client.post(
            f"/support/queue/{ticket['id']}/{action}", headers=world.as_staff(world.boris)
        )
        assert response.status_code == 403, action


def test_admin_takes_like_anyone_and_supervises_taken_tickets(world: World) -> None:
    taken_by_anna = world.take(world.open(), world.anna)

    again = world.client.post(
        f"/support/queue/{taken_by_anna['id']}/take", headers=world.as_admin()
    )
    assert again.status_code == 409
    reply = world.client.post(
        f"/support/queue/{taken_by_anna['id']}/messages",
        json={"text": "Подключился руководитель"},
        headers=world.as_admin(),
    )
    assert reply.status_code == 201
    assert reply.json()["assignee_id"] == str(world.anna)
    assert reply.json()["messages"][-1]["author_name"] == "Алексей Админов"

    free = world.open()
    early = world.client.post(
        f"/support/queue/{free['id']}/messages", json={"text": "Сразу"}, headers=world.as_admin()
    )
    assert early.status_code == 409
    took = world.client.post(f"/support/queue/{free['id']}/take", headers=world.as_admin())
    assert took.json()["assignee_id"] == str(world.admin)


# --- rights -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/support/queue"),
        ("get", "/support/queue/{id}"),
        ("post", "/support/queue/{id}/take"),
        ("post", "/support/queue/{id}/release"),
        ("post", "/support/queue/{id}/resolve"),
        ("post", "/support/queue/{id}/close"),
    ],
)
def test_client_has_no_access_to_the_queue(world: World, method: str, path: str) -> None:
    ticket = world.open()

    response = world.client.request(
        method, path.format(id=ticket["id"]), headers=world.as_client(world.director)
    )

    assert response.status_code == 403


def test_client_cannot_answer_as_staff(world: World) -> None:
    ticket = world.open()

    response = world.client.post(
        f"/support/queue/{ticket['id']}/messages",
        json={"text": "Сам себе отвечу"},
        headers=world.as_client(world.director),
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/support/tickets"),
        ("post", "/support/tickets"),
        ("get", "/support/tickets/{id}"),
        ("post", "/support/tickets/{id}/close"),
    ],
)
def test_staff_does_not_use_the_client_side(world: World, method: str, path: str) -> None:
    ticket = world.open()

    response = world.client.request(
        method,
        path.format(id=ticket["id"]),
        json={"subject": "Вопрос", "text": "Текст"},
        headers=world.as_staff(world.anna),
    )

    assert response.status_code == 403


def test_without_a_token_is_401(world: World) -> None:
    assert world.client.get("/support/tickets").status_code == 401
    assert world.client.get("/support/queue").status_code == 401


def test_unknown_ticket_is_404(world: World) -> None:
    response = world.client.post(
        "/support/queue/00000000-0000-0000-0000-000000000000/take",
        headers=world.as_staff(world.anna),
    )

    assert response.status_code == 404
