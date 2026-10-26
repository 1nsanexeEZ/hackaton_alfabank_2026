"""The client's side of support: open, read own tickets, write, close."""

from uuid import uuid4

import pytest

from tests.support.api.conftest import World


def test_client_opens_a_ticket_with_the_first_message(world: World) -> None:
    ticket = world.open(subject="Вопрос по <b>ставке</b>", text="Почему <i>24</i> %?")

    assert ticket["number"] == "ТП-2026-000001"
    assert ticket["status"] == "open"
    assert ticket["subject"] == "Вопрос по ставке"
    assert ticket["author_id"] == str(world.director)
    assert ticket["author_name"] == "Иван Ромашкин"
    assert ticket["assignee_id"] is None
    assert (ticket["organization_id"], ticket["application_id"]) == (None, None)
    assert ticket["message_count"] == 1
    assert ticket["last_message_side"] == "client"
    [message] = ticket["messages"]
    assert (message["side"], message["text"], message["author_name"]) == (
        "client",
        "Почему 24 %?",
        "Иван Ромашкин",
    )
    assert world.outbox_types() == ["SupportTicketOpened"]
    assert world.open()["number"] == "ТП-2026-000002"


def test_ticket_about_a_company_of_the_client(world: World) -> None:
    ticket = world.open(organization_id=str(world.romashka))

    assert ticket["organization_id"] == str(world.romashka)


def test_ticket_about_an_application_takes_its_company(world: World) -> None:
    ticket = world.open(application_id=str(world.card.id))

    assert ticket["application_id"] == str(world.card.id)
    assert ticket["organization_id"] == str(world.romashka)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"organization_id": "vector"}, id="foreign-company"),
        pytest.param({"application_id": "card", "who": "petrov"}, id="foreign-application"),
        pytest.param({"application_id": "unknown"}, id="unknown-application"),
    ],
)
def test_a_stranger_company_or_application_is_not_found(world: World, body: dict) -> None:
    ids = {"vector": str(world.vector), "card": str(world.card.id), "unknown": str(uuid4())}
    who = world.petrov if body.pop("who", None) else world.director
    payload = {"subject": "Вопрос", "text": "Текст"} | {k: ids[v] for k, v in body.items()}

    response = world.client.post("/support/tickets", json=payload, headers=world.as_client(who))

    assert response.status_code == 404, response.text


def test_application_of_another_company_than_named_is_rejected(world: World) -> None:
    payload = {
        "subject": "Вопрос",
        "text": "Текст",
        "organization_id": str(world.vector),
        "application_id": str(world.card.id),
    }

    # Petrov is not a member of «Ромашка»: 404 comes first, the mismatch is not revealed.
    stranger = world.client.post(
        "/support/tickets", json=payload, headers=world.as_client(world.petrov)
    )
    member = world.client.post(
        "/support/tickets", json=payload, headers=world.as_client(world.director)
    )

    assert stranger.status_code == 404
    assert member.status_code == 422, member.text
    assert member.json()["details"] == {"field": "application_id"}


@pytest.mark.parametrize(
    "payload",
    [
        {"subject": "Вопрос", "text": ""},
        {"subject": "Вопрос", "text": "   "},
        {"subject": "Вопрос", "text": "<b></b>"},
        {"subject": "", "text": "Текст"},
        {"text": "Текст"},
        {"subject": "Вопрос", "text": "я" * 4001},
    ],
    ids=["empty", "blank", "only-html", "empty-subject", "no-subject", "too-long"],
)
def test_empty_or_too_long_text_is_422(world: World, payload: dict) -> None:
    response = world.client.post(
        "/support/tickets", json=payload, headers=world.as_client(world.director)
    )

    assert response.status_code == 422, response.text


def test_client_sees_only_own_tickets(world: World) -> None:
    own = world.open(world.director)
    colleague = world.open(world.accountant, organization_id=str(world.romashka))

    mine = world.client.get("/support/tickets", headers=world.as_client(world.director))
    assert [t["id"] for t in mine.json()] == [own["id"]]
    assert mine.headers["X-Total-Count"] == "1"
    queue = world.client.get("/support/queue", params={"limit": 1}, headers=world.as_admin())
    assert len(queue.json()) == 1 and queue.headers["X-Total-Count"] == "2"
    # A colleague from the same company is not a reason to see the ticket.
    stranger = world.client.get(
        f"/support/tickets/{colleague['id']}", headers=world.as_client(world.director)
    )
    assert stranger.status_code == 404
    write = world.client.post(
        f"/support/tickets/{colleague['id']}/messages",
        json={"text": "Чужое"},
        headers=world.as_client(world.director),
    )
    assert write.status_code == 404
    close = world.client.post(
        f"/support/tickets/{colleague['id']}/close", headers=world.as_client(world.director)
    )
    assert close.status_code == 404


def test_client_reads_the_chat_and_filters_by_status(world: World) -> None:
    first = world.open()
    second = world.open(subject="Второй вопрос")
    world.take(first)

    card = world.client.get(
        f"/support/tickets/{first['id']}", headers=world.as_client(world.director)
    )
    assert card.status_code == 200
    assert card.json()["assignee_name"] == "Анна Аналитикова"

    in_progress = world.client.get(
        "/support/tickets",
        params={"status": "in_progress"},
        headers=world.as_client(world.director),
    )
    assert [t["id"] for t in in_progress.json()] == [first["id"]]
    both = world.client.get(
        "/support/tickets",
        params=[("status", "open"), ("status", "in_progress")],
        headers=world.as_client(world.director),
    )
    assert {t["id"] for t in both.json()} == {first["id"], second["id"]}


def test_client_writes_into_own_ticket(world: World) -> None:
    ticket = world.open()

    response = world.client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"text": "Забыл: заявка КР-2026-000001"},
        headers=world.as_client(world.director),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "open"
    assert [m["text"] for m in body["messages"]] == [
        "Загрузил выписку, её нет в заявке",
        "Забыл: заявка КР-2026-000001",
    ]
    assert body["version"] == ticket["version"] + 1


def test_client_closes_own_ticket_and_nobody_writes_there_anymore(world: World) -> None:
    ticket = world.open()

    closed = world.client.post(
        f"/support/tickets/{ticket['id']}/close", headers=world.as_client(world.director)
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"] is not None

    again = world.client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"text": "Ещё вопрос"},
        headers=world.as_client(world.director),
    )
    assert again.status_code == 409
    assert again.json()["details"]["code"] == "ticket_closed"
    twice = world.client.post(
        f"/support/tickets/{ticket['id']}/close", headers=world.as_client(world.director)
    )
    assert twice.status_code == 409
    assert twice.json()["code"] == "invalid_transition"


def test_admin_reads_any_ticket_but_does_not_write_as_the_client(world: World) -> None:
    ticket = world.open()

    listed = world.client.get("/support/tickets", headers=world.as_admin())
    assert [t["id"] for t in listed.json()] == [ticket["id"]]
    write = world.client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"text": "От имени клиента"},
        headers=world.as_admin(),
    )
    assert write.status_code == 403
    assert write.json()["details"]["code"] == "not_author"
