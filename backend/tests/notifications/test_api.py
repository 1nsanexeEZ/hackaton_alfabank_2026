"""HTTP: feed, read marks, personal news, SSE tickets. Events reach the feed
through the real messaging runtime (manual mode, drain)."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from seed.notifications import seed as seed_news
from seed.run import SeedContext
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.applications import ApplicationSubmitted
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.process import UserTaskCreated
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.main import create_app
from src.modules.notifications.application.use_cases import stream
from tests.fakes import builders
from tests.helpers import bearer, create_schema, token_for
from tests.notifications.conftest import World

CLIENT = [Permissions.FEED_READ]
UNDERWRITER = [Permissions.FEED_READ, Permissions.BACKOFFICE_READ]


@dataclass
class Api:
    client: TestClient
    world: World
    clock: FrozenClock

    def token(self, account_id: UUID, permissions: list[Permissions] = CLIENT) -> dict[str, str]:
        return bearer(token_for(self.client.app, permissions, subject=account_id))  # type: ignore[arg-type]

    def publish(self, *messages: IntegrationMessage) -> None:
        app = self.client.app

        async def run() -> None:
            async with app.state.session_factory() as session:  # type: ignore[attr-defined]
                writer = SqlAlchemyOutboxWriter(session, "test", self.clock)
                for message in messages:
                    key = getattr(message, "application_id", None) or message.organization_id  # type: ignore[attr-defined]
                    await writer.add(message, key=key, correlation_id=key)
                await session.commit()
            await app.state.messaging.drain()  # type: ignore[attr-defined]

        assert self.client.portal is not None
        self.client.portal.call(run)

    def seed_news(self) -> None:
        app = self.client.app
        context = SeedContext(
            app.state.settings,  # type: ignore[attr-defined]
            app.state.session_factory,  # type: ignore[attr-defined]
            app.state.facades,  # type: ignore[attr-defined]
            self.clock,
        )
        assert self.client.portal is not None
        self.client.portal.call(seed_news, context)


@pytest.fixture
def api(settings: Settings, world: World) -> Iterator[Api]:
    create_schema(settings.database_url)
    clock = FrozenClock(builders.NOW)
    app = create_app(settings, clock=clock)
    world.register(app.state.facades)
    with TestClient(app) as client:
        yield Api(client, world, clock)


def submitted(world: World) -> ApplicationSubmitted:
    return ApplicationSubmitted(
        application_id=world.card.id,
        organization_id=world.romashka.id,
        product_code="UNSECURED",
        amount=Decimal("3000000"),
        term_months=24,
        purpose="working_capital",
    )


def task_created(world: World) -> UserTaskCreated:
    return UserTaskCreated(
        task_id=uuid4(),
        process_id=uuid4(),
        application_id=world.card.id,
        task_type="underwriting_review",
        candidate_role="underwriter",
    )


# --- feed ----------------------------------------------------------------------


def test_feed_needs_a_token_with_feed_read(api: Api) -> None:
    assert api.client.get("/feed").status_code == 401
    headers = api.token(api.world.director, [Permissions.REQUESTS_READ])
    assert api.client.get("/feed", headers=headers).status_code == 403


def test_members_see_their_company_feed(api: Api) -> None:
    world = api.world
    api.publish(submitted(world))

    for account in (world.director, world.accountant):
        page = api.client.get("/feed", headers=api.token(account)).json()
        assert page["total"] == 1
        [item] = page["items"]
        assert item["audience"] == "client" and item["type"] == "status_changed"
        assert item["title"] == "Заявка № КР-2026-000001 отправлена в банк"
        assert item["organization_id"] == str(world.romashka.id) and item["read_at"] is None

    stranger = api.client.get("/feed", headers=api.token(world.stranger)).json()
    assert stranger["items"] == [] and stranger["total"] == 0


def test_filter_by_someone_elses_company_is_404(api: Api) -> None:
    world = api.world
    api.publish(submitted(world))
    headers = api.token(world.director)
    own = api.client.get(
        "/feed", params={"organization_id": str(world.romashka.id)}, headers=headers
    )
    assert own.status_code == 200 and own.json()["total"] == 1
    for path in ("/feed", "/feed/unread-count", "/news"):
        response = api.client.get(
            path, params={"organization_id": str(world.ivanov.id)}, headers=headers
        )
        assert response.status_code == 404, path
    response = api.client.post(
        "/feed/read-all", params={"organization_id": str(world.ivanov.id)}, headers=headers
    )
    assert response.status_code == 404


def test_read_marks(api: Api) -> None:
    world = api.world
    api.publish(submitted(world), task_created(world))
    director, accountant = api.token(world.director), api.token(world.accountant)
    assert api.client.get("/feed/unread-count", headers=director).json() == {"count": 1}

    [item] = api.client.get("/feed", headers=director).json()["items"]
    foreign = api.client.post(f"/feed/{item['id']}/read", headers=api.token(world.ivanov_owner))
    assert foreign.status_code == 404, "someone else's record does not exist for you"
    assert api.client.post(f"/feed/{uuid4()}/read", headers=director).status_code == 404

    read = api.client.post(f"/feed/{item['id']}/read", headers=director)
    assert read.status_code == 200 and read.json()["read_at"] is not None
    again = api.client.post(f"/feed/{item['id']}/read", headers=director).json()
    assert again["read_at"] == read.json()["read_at"], "reading twice keeps the first mark"
    assert api.client.get("/feed/unread-count", headers=director).json() == {"count": 0}
    unread = api.client.get("/feed", params={"unread_only": True}, headers=director).json()
    assert unread["items"] == []

    # the accountant's copy is separate
    assert api.client.get("/feed/unread-count", headers=accountant).json() == {"count": 1}
    assert api.client.post("/feed/read-all", headers=accountant).json() == {"updated": 1}
    assert api.client.get("/feed/unread-count", headers=accountant).json() == {"count": 0}


def test_underwriter_reads_the_back_office_feed(api: Api) -> None:
    world = api.world
    api.publish(submitted(world), task_created(world))
    headers = api.token(uuid4(), UNDERWRITER)

    page = api.client.get("/feed", headers=headers).json()
    assert [i["type"] for i in page["items"]] == ["task_assigned", "status_changed"]
    assert {i["audience"] for i in page["items"]} == {"bank"}
    assert page["items"][0]["action_required"] is True
    # bank staff may look at any company
    response = api.client.get(
        "/feed", params={"organization_id": str(world.romashka.id)}, headers=headers
    )
    assert response.status_code == 200 and response.json()["total"] == 2
    paged = api.client.get("/feed", params={"limit": 1, "offset": 1}, headers=headers).json()
    assert [i["type"] for i in paged["items"]] == ["status_changed"] and paged["total"] == 2


# --- news ----------------------------------------------------------------------


def test_personal_news_differ_by_company(api: Api) -> None:
    world = api.world
    api.seed_news()

    romashka = api.client.get(
        "/news",
        params={"organization_id": str(world.romashka.id)},
        headers=api.token(world.director),
    ).json()
    ivanov = api.client.get(
        "/news",
        params={"organization_id": str(world.ivanov.id)},
        headers=api.token(world.ivanov_owner),
    ).json()
    assert len(romashka) == len(ivanov) == 5
    assert [n["id"] for n in romashka] != [n["id"] for n in ivanov]
    assert romashka[0]["relevance"] == ["ОКВЭД 56.10 — общепит"]
    assert ivanov[0]["relevance"] == ["ОКВЭД 62 — разработка ПО"]
    assert not any(n["read"] for n in romashka)

    general = api.client.get("/news", headers=api.token(world.director)).json()
    assert {tuple(n["relevance"]) for n in general} == {("для всех клиентов",)}


def test_news_read_mark(api: Api) -> None:
    world = api.world
    api.seed_news()
    headers = api.token(world.director)
    params = {"organization_id": str(world.romashka.id)}
    first = api.client.get("/news", params=params, headers=headers).json()[0]

    assert api.client.post(f"/news/{first['id']}/read", headers=headers).status_code == 204
    assert api.client.post(f"/news/{first['id']}/read", headers=headers).status_code == 204
    assert api.client.get("/news", params=params, headers=headers).json()[0]["read"] is True
    accountant = api.client.get("/news", params=params, headers=api.token(world.accountant))
    assert accountant.json()[0]["read"] is False
    assert api.client.post(f"/news/{uuid4()}/read", headers=headers).status_code == 404


# --- SSE -------------------------------------------------------------------------


def parse_sse(text: str) -> list[dict[str, str]]:
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.split("\n"):
            if ":" in line and not line.startswith(":"):
                name, _, value = line.partition(":")
                fields[name] = value.strip()
        if fields:
            events.append(fields)
    return events


@pytest.fixture
def short_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream, "POLL_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(stream, "MAX_STREAM_SECONDS", 0.3)


def ticket_for(api: Api, account_id: UUID) -> dict:
    response = api.client.post("/feed/stream-ticket", headers=api.token(account_id))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.usefixtures("short_stream")
def test_stream_sends_feed_records_and_spends_the_ticket(api: Api) -> None:
    world = api.world
    api.publish(submitted(world))
    ticket = ticket_for(api, world.director)
    assert ticket["expires_in"] == 30
    assert ticket["stream_url"] == f"/feed/stream?ticket={ticket['ticket']}"

    response = api.client.get(
        "/feed/stream", params={"ticket": ticket["ticket"], "last_event_id": "0"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [e["event"] for e in events] == ["feed_item", "application_updated"]
    item = json.loads(events[0]["data"])
    assert item["title"] == "Заявка № КР-2026-000001 отправлена в банк"
    assert events[0]["id"] == str(item["seq"]) == events[1]["id"]
    assert json.loads(events[1]["data"])["application_id"] == str(world.card.id)

    again = api.client.get("/feed/stream", params={"ticket": ticket["ticket"]})
    assert again.status_code == 401, "a ticket works once"


@pytest.mark.usefixtures("short_stream")
def test_stream_resumes_after_last_event_id(api: Api) -> None:
    world = api.world
    api.publish(submitted(world))
    first = parse_sse(
        api.client.get(
            "/feed/stream",
            params={"ticket": ticket_for(api, world.director)["ticket"], "last_event_id": "0"},
        ).text
    )
    last_id = first[-1]["id"]
    resumed = api.client.get(
        "/feed/stream",
        params={"ticket": ticket_for(api, world.director)["ticket"]},
        headers={"Last-Event-ID": last_id},
    )
    assert [e["event"] for e in parse_sse(resumed.text) if e.get("event") != "heartbeat"] == []


def test_expired_or_unknown_ticket_is_401(api: Api) -> None:
    ticket = ticket_for(api, api.world.director)["ticket"]
    api.clock.advance(timedelta(seconds=31))
    assert api.client.get("/feed/stream", params={"ticket": ticket}).status_code == 401
    assert api.client.get("/feed/stream", params={"ticket": "nope"}).status_code == 401
    assert api.client.post("/feed/stream-ticket").status_code == 401
