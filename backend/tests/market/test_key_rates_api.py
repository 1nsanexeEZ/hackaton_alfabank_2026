"""The key rate history through the API, on a frozen Moscow day (2026-10-21, 15:00 МСК)."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from seed.products import seed
from seed.run import SeedContext
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.market import KeyRateChanged
from src.core.messaging.outbox import OutboxRecord
from src.main import create_app
from src.modules.decision import module as decision_module
from src.modules.market import module as market_module
from tests.helpers import bearer, create_schema, token_for

TODAY = "2026-10-21"
TOMORROW = "2026-10-22"
YESTERDAY = "2026-10-20"


@dataclass
class World:
    api: TestClient
    clock: FrozenClock
    reader: dict[str, str]
    editor: dict[str, str]


async def _seed_products(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed(SeedContext(settings, sessions, FacadeRegistry(), FrozenClock()))
    await engine.dispose()


@pytest.fixture
def world(settings: Settings) -> Iterator[World]:
    create_schema(settings.database_url)
    asyncio.run(_seed_products(settings))
    clock = FrozenClock()
    app = create_app(settings, clock=clock)
    with TestClient(app) as api:
        reader = bearer(token_for(app, [Permissions.SCORING_READ]))
        editor = bearer(token_for(app, [Permissions.SCORING_READ, Permissions.SCORING_UPDATE]))
        yield World(api, clock, reader, editor)


def add(world: World, value: str, effective_from: str, **extra: str) -> dict:
    response = world.api.post(
        "/market/key-rates",
        json={"value": value, "effective_from": effective_from, **extra},
        headers=world.editor,
    )
    assert response.status_code == 201, response.text
    return response.json()


def current(world: World, on: str | None = None) -> dict:
    response = world.api.get("/market/key-rate", params={"on": on} if on else None)
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_history_gives_the_settings_value(world: World) -> None:
    """Tests pin KEY_RATE=16.50 (tests/conftest.py)."""
    assert current(world) == {"value": "16.50", "effective_from": None, "source": "settings"}
    history = world.api.get("/market/key-rates", headers=world.reader).json()
    assert history == {"current": current(world), "items": []}


def test_rate_from_today_is_in_force_at_once(world: World) -> None:
    record = add(world, "14.00", TODAY, decided_on=YESTERDAY, note="решение СД")
    assert record["in_force"] and record["removable"]
    assert record["source"] == "admin" and record["decided_on"] == YESTERDAY
    assert current(world) == {"value": "14.00", "effective_from": TODAY, "source": "admin"}
    assert current(world, on=YESTERDAY)["source"] == "settings"


def test_future_rate_is_in_force_from_its_date(world: World) -> None:
    add(world, "14.00", YESTERDAY)
    future = add(world, "13.50", TOMORROW)
    assert not future["in_force"] and future["removable"]
    assert current(world)["value"] == "14.00"
    assert current(world, on=TOMORROW)["value"] == "13.50"

    history = world.api.get("/market/key-rates", headers=world.reader).json()
    assert [(i["effective_from"], i["in_force"], i["removable"]) for i in history["items"]] == [
        (TOMORROW, False, True),
        (YESTERDAY, True, False),
    ]

    world.clock.advance(timedelta(days=1))
    assert current(world) == {"value": "13.50", "effective_from": TOMORROW, "source": "admin"}


def test_moscow_day_decides(world: World) -> None:
    """21:30 UTC on the 21st is already the 22nd in Moscow."""
    add(world, "13.50", TOMORROW)
    world.clock.advance(timedelta(hours=9, minutes=30))
    assert current(world)["value"] == "13.50"


def test_date_is_taken(world: World) -> None:
    add(world, "14.00", TOMORROW)
    response = world.api.post(
        "/market/key-rates", json={"value": "13", "effective_from": TOMORROW}, headers=world.editor
    )
    assert response.status_code == 409 and response.json()["code"] == "conflict"


@pytest.mark.parametrize(
    "body",
    [
        {"value": "101", "effective_from": TODAY},
        {"value": "-1", "effective_from": TODAY},
        {"value": "13.555", "effective_from": TODAY},
        {"value": "13", "effective_from": TODAY, "decided_on": TOMORROW},
        {"value": "13", "effective_from": TODAY, "note": "х" * 501},
    ],
)
def test_invalid_rate_is_refused(world: World, body: dict) -> None:
    response = world.api.post("/market/key-rates", json=body, headers=world.editor)
    assert response.status_code == 422, response.text


def test_only_future_or_todays_rate_is_removed(world: World) -> None:
    add(world, "14.00", YESTERDAY)
    add(world, "13.75", TODAY)
    add(world, "13.50", TOMORROW)

    past = world.api.delete(f"/market/key-rates/{YESTERDAY}", headers=world.editor)
    assert past.status_code == 409 and past.json()["code"] == "invalid_transition"
    assert (
        world.api.delete(f"/market/key-rates/{TOMORROW}", headers=world.editor).status_code == 204
    )
    assert world.api.delete(f"/market/key-rates/{TODAY}", headers=world.editor).status_code == 204
    assert current(world)["value"] == "14.00"
    missing = world.api.delete(f"/market/key-rates/{TOMORROW}", headers=world.editor)
    assert missing.status_code == 404


def test_rights(world: World) -> None:
    body = {"value": "13", "effective_from": TOMORROW}
    assert world.api.get("/market/key-rates").status_code == 401
    assert world.api.post("/market/key-rates", json=body).status_code == 401
    assert world.api.post("/market/key-rates", json=body, headers=world.reader).status_code == 403
    assert (
        world.api.delete(f"/market/key-rates/{TOMORROW}", headers=world.reader).status_code == 403
    )
    assert world.api.get("/market/key-rates", headers=world.reader).status_code == 200


def test_catalog_rates_follow_the_rate_in_force(world: World) -> None:
    """The catalog is set at 16.50: a key rate of 14 moves it by -2.5 — from tomorrow on."""

    def unsecured() -> Decimal:
        return Decimal(world.api.get("/products/UNSECURED").json()["rate_base"])

    assert unsecured() == Decimal("23.5")
    add(world, "14.00", TOMORROW)
    assert unsecured() == Decimal("23.5")
    world.clock.advance(timedelta(days=1))
    assert unsecured() == Decimal("21.0")
    # Keeping the catalog sees the stored rates.
    stored = world.api.get(
        "/products/all", headers=bearer(token_for(world.api.app, [Permissions.CREDITS_UPDATE]))
    )
    assert stored.status_code == 200, stored.text
    assert Decimal(stored.json()[0]["rate_base"]) == Decimal("23.5")


# --- KeyRateChanged ------------------------------------------------------------------


def announced(world: World, settings: Settings) -> list[dict]:
    async def read() -> list[dict]:
        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            stmt = (
                select(OutboxRecord.envelope)
                .where(OutboxRecord.message_type == KeyRateChanged.TYPE)
                .order_by(OutboxRecord.id)
            )
            rows = list((await conn.scalars(stmt)).all())
        await engine.dispose()
        return [row["payload"] for row in rows]

    return asyncio.run(read())


def test_rate_from_today_is_announced_at_once(world: World, settings: Settings) -> None:
    add(world, "14.00", TODAY)
    assert announced(world, settings) == [{"value": "14.00", "effective_from": TODAY}]
    # The job has nothing left to send.
    assert world.api.portal.call(market_module.announce_due_once, world.api.app) == 0


def test_rate_entered_ahead_is_announced_on_its_day_once(world: World, settings: Settings) -> None:
    add(world, "13.50", TOMORROW)
    assert announced(world, settings) == []
    assert world.api.portal.call(market_module.announce_due_once, world.api.app) == 0

    world.clock.advance(timedelta(days=1))
    assert world.api.portal.call(market_module.announce_due_once, world.api.app) == 1
    assert world.api.portal.call(market_module.announce_due_once, world.api.app) == 0
    assert announced(world, settings) == [{"value": "13.50", "effective_from": TOMORROW}]


def test_removing_todays_rate_announces_the_previous_one(world: World, settings: Settings) -> None:
    add(world, "14.00", YESTERDAY)
    add(world, "13.75", TODAY)
    assert world.api.delete(f"/market/key-rates/{TODAY}", headers=world.editor).status_code == 204
    assert announced(world, settings)[-1] == {"value": "14.00", "effective_from": YESTERDAY}


def test_key_rate_changed_wakes_the_pre_approval_refresh(world: World) -> None:
    wake = decision_module._current().wake
    wake.clear()
    world.api.portal.call(
        decision_module._on_key_rate_changed, None, KeyRateChanged(value=Decimal("14"))
    )
    assert wake.is_set()
