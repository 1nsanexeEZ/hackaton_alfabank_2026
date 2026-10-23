"""Personal consents: `/me/consents` and `IdentityFacade.get_active_consent`."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.main import create_app
from src.modules.identity.domain.entities import add_months
from src.modules.identity.facade import ConsentDTO, ConsentType, IdentityFacade
from src.modules.identity.infrastructure.database.models import ConsentModel
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, auth
from tests.helpers import create_schema

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
SIX_MONTHS_LATER = "2027-04-21T12:00:00Z"


@dataclass
class World:
    client: TestClient
    clock: FrozenClock
    token: str
    account_id: UUID

    def give(self, *types: str, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
        response = self.client.post(
            "/me/consents",
            json={"types": list(types)},
            headers={**auth(self.token), **(headers or {})},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def consents(self) -> list[dict[str, Any]]:
        response = self.client.get("/me/consents", headers=auth(self.token))
        assert response.status_code == 200, response.text
        return response.json()

    def revoke(self, type: str) -> None:
        response = self.client.delete(f"/me/consents/{type}", headers=auth(self.token))
        assert response.status_code == 204, response.text

    def active(self, type: ConsentType, account_id: UUID | None = None) -> ConsentDTO | None:
        app = self.client.app

        async def load() -> ConsentDTO | None:
            async with app.state.session_factory() as session:  # type: ignore[attr-defined]
                identity = app.state.facades.get(IdentityFacade, session)  # type: ignore[attr-defined]
                return await identity.get_active_consent(account_id or self.account_id, type)

        return self.client.portal.call(load)  # type: ignore[union-attr]

    def rows(self) -> list[ConsentModel]:
        app = self.client.app

        async def load() -> list[ConsentModel]:
            async with app.state.session_factory() as session:  # type: ignore[attr-defined]
                return list((await session.scalars(select(ConsentModel))).all())

        return self.client.portal.call(load)  # type: ignore[union-attr]


@pytest.fixture
def world(settings: Settings) -> Iterator[World]:
    clock = FrozenClock(NOW)
    create_schema(settings.database_url)
    with TestClient(create_app(settings, clock=clock)) as client:
        response = client.post(
            "/auth/login", json={"login": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        token = response.json()["access_token"]
        me = client.get("/me", headers=auth(token)).json()
        yield World(client, clock, token, UUID(me["id"]))


def test_personal_data_is_open_ended_and_bureau_lasts_six_months(world: World) -> None:
    given = world.give("personal_data", "credit_bureau_personal")

    assert given == [
        {
            "type": "personal_data",
            "given_at": "2026-10-21T12:00:00Z",
            "valid_until": None,
            "revoked_at": None,
            "active": True,
            "text_version": "pd-2026-10",
        },
        {
            "type": "credit_bureau_personal",
            "given_at": "2026-10-21T12:00:00Z",
            "valid_until": SIX_MONTHS_LATER,
            "revoked_at": None,
            "active": True,
            "text_version": "bki-fl-2026-10",
        },
    ]
    assert sorted(c["type"] for c in world.consents()) == [
        "credit_bureau_personal",
        "personal_data",
    ]


def test_bureau_consent_runs_out(world: World) -> None:
    world.give("personal_data", "credit_bureau_personal")

    world.clock.set(datetime(2027, 4, 21, 11, 59, 59, tzinfo=UTC))
    consent = world.active("credit_bureau_personal")
    assert consent is not None and consent.given_at == NOW
    assert consent.valid_until == datetime(2027, 4, 21, 12, 0, tzinfo=UTC)

    world.clock.advance(timedelta(seconds=1))
    assert world.active("credit_bureau_personal") is None
    by_type = {c["type"]: c for c in world.consents()}
    assert by_type["credit_bureau_personal"]["active"] is False
    assert by_type["credit_bureau_personal"]["revoked_at"] is None

    world.clock.advance(timedelta(days=3650))
    assert world.active("personal_data") is not None
    assert {c["type"]: c["active"] for c in world.consents()}["personal_data"] is True


def test_revoke_closes_the_consent_and_repeats_quietly(world: World) -> None:
    world.give("personal_data", "credit_bureau_personal")
    world.clock.advance(timedelta(days=1))

    world.revoke("credit_bureau_personal")
    world.clock.advance(timedelta(days=1))
    world.revoke("credit_bureau_personal")

    by_type = {c["type"]: c for c in world.consents()}
    assert by_type["credit_bureau_personal"]["revoked_at"] == "2026-10-22T12:00:00Z"
    assert by_type["credit_bureau_personal"]["active"] is False
    assert by_type["personal_data"]["active"] is True
    assert world.active("credit_bureau_personal") is None
    assert world.active("personal_data") is not None


def test_revoking_a_consent_never_given_is_204(world: World) -> None:
    world.revoke("credit_bureau_personal")

    assert world.consents() == []


def test_history_keeps_every_consent(world: World) -> None:
    world.give("credit_bureau_personal")
    world.clock.advance(timedelta(days=1))
    world.revoke("credit_bureau_personal")
    world.clock.advance(timedelta(days=1))
    world.give("credit_bureau_personal")

    history = world.consents()
    assert [(c["given_at"], c["revoked_at"], c["active"]) for c in history] == [
        ("2026-10-23T12:00:00Z", None, True),
        ("2026-10-21T12:00:00Z", "2026-10-22T12:00:00Z", False),
    ]
    consent = world.active("credit_bureau_personal")
    assert consent is not None
    assert consent.given_at == datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
    assert consent.valid_until == datetime(2027, 4, 23, 12, 0, tzinfo=UTC)


def test_a_new_consent_does_not_rewrite_the_old_one(world: World) -> None:
    world.give("credit_bureau_personal")
    world.clock.advance(timedelta(days=30))
    world.give("credit_bureau_personal")

    assert [c["active"] for c in world.consents()] == [True, True]
    consent = world.active("credit_bureau_personal")
    assert consent is not None and consent.given_at == NOW + timedelta(days=30)


def test_run_out_consent_is_not_marked_revoked(world: World) -> None:
    world.give("credit_bureau_personal")
    world.clock.advance(timedelta(days=200))

    world.revoke("credit_bureau_personal")

    assert world.consents()[0]["revoked_at"] is None


def test_consent_keeps_the_request_origin(world: World) -> None:
    world.give("personal_data", headers={"User-Agent": "Cabinet/1.0"})

    [row] = world.rows()
    assert row.account_id == world.account_id
    assert row.ip == "testclient"
    assert row.user_agent == "Cabinet/1.0"


def test_somebody_elses_consent_does_not_count(world: World) -> None:
    world.give("credit_bureau_personal")

    assert world.active("credit_bureau_personal", account_id=uuid4()) is None


@pytest.mark.parametrize(
    "body",
    [{"types": []}, {"types": ["credit_bureau"]}, {}],
    ids=["empty", "company_consent", "missing"],
)
def test_bad_consent_request_is_422(world: World, body: dict[str, Any]) -> None:
    response = world.client.post("/me/consents", json=body, headers=auth(world.token))
    assert response.status_code == 422


def test_unknown_type_cannot_be_revoked(world: World) -> None:
    response = world.client.delete("/me/consents/marketing", headers=auth(world.token))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "method,path", [("GET", "/me/consents"), ("DELETE", "/me/consents/personal_data")]
)
def test_consents_need_a_token(world: World, method: str, path: str) -> None:
    assert world.client.request(method, path).status_code == 401


@pytest.mark.parametrize(
    "moment,expected",
    [
        (datetime(2026, 10, 21, 12, tzinfo=UTC), datetime(2027, 4, 21, 12, tzinfo=UTC)),
        (datetime(2026, 8, 31, tzinfo=UTC), datetime(2027, 2, 28, tzinfo=UTC)),
        (datetime(2027, 8, 31, tzinfo=UTC), datetime(2028, 2, 29, tzinfo=UTC)),
        (datetime(2026, 12, 15, tzinfo=UTC), datetime(2027, 6, 15, tzinfo=UTC)),
    ],
)
def test_six_months_are_calendar_months(moment: datetime, expected: datetime) -> None:
    assert add_months(moment, 6) == expected
