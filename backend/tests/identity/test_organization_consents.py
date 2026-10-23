"""Company consents: `/organizations/{id}/consents` and
`IdentityFacade.get_active_organization_consent`. Rights inside the company come from
a FakeClientsFacade (clients is another module)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.main import create_app
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import ConsentDTO, IdentityFacade
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, auth
from tests.fakes import builders, install
from tests.fakes.clients_facade import FakeClientsFacade
from tests.helpers import create_schema

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
PASSWORD = "Second-password-1"


@dataclass
class World:
    client: TestClient
    clock: FrozenClock
    clients: FakeClientsFacade
    organization_id: UUID
    # Director of the company (the bootstrap admin plays them) and an accountant.
    director: UUID
    director_token: str
    accountant: UUID
    accountant_token: str

    def url(self, organization_id: UUID | None = None) -> str:
        return f"/organizations/{organization_id or self.organization_id}/consents"

    def give(self, token: str | None = None, **kw: Any) -> list[dict[str, Any]]:
        response = self.client.post(
            self.url(),
            json={"types": ["credit_bureau_company"]},
            headers={**auth(token or self.director_token), **kw.get("headers", {})},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def consents(self, token: str | None = None) -> list[dict[str, Any]]:
        response = self.client.get(self.url(), headers=auth(token or self.director_token))
        assert response.status_code == 200, response.text
        return response.json()

    def revoke(self, token: str | None = None) -> None:
        response = self.client.delete(
            f"{self.url()}/credit_bureau_company", headers=auth(token or self.director_token)
        )
        assert response.status_code == 204, response.text

    def active(self, organization_id: UUID | None = None) -> ConsentDTO | None:
        app = self.client.app

        async def load() -> ConsentDTO | None:
            async with app.state.session_factory() as session:  # type: ignore[attr-defined]
                identity = app.state.facades.get(IdentityFacade, session)  # type: ignore[attr-defined]
                return await identity.get_active_organization_consent(
                    organization_id or self.organization_id, "credit_bureau_company"
                )

        return self.client.portal.call(load)  # type: ignore[union-attr]


@pytest.fixture
def world(settings: Settings) -> Iterator[World]:
    clock = FrozenClock(NOW)
    create_schema(settings.database_url)
    app = create_app(settings, clock=clock)
    clients = install(app, ClientsFacade, FakeClientsFacade())
    organization_id = clients.add_organization(builders.organization_snapshot("romashka")).id
    with TestClient(app) as client:
        login = {"login": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        director_token = client.post("/auth/login", json=login).json()["access_token"]
        me = client.get("/me", headers=auth(director_token)).json()
        created = client.post(
            "/accounts",
            json={
                "email": "accountant@romashka.ru",
                "password": PASSWORD,
                "role_id": me["role"]["id"],
                "profile": {"last_name": "Петрова", "first_name": "Анна"},
            },
            headers=auth(director_token),
        )
        assert created.status_code == 201, created.text
        login = {"login": "accountant@romashka.ru", "password": PASSWORD}
        accountant_token = client.post("/auth/login", json=login).json()["access_token"]
        director, accountant = UUID(me["id"]), UUID(created.json()["id"])
        clients.add_member(director, organization_id, "director")
        clients.add_member(accountant, organization_id, "accountant")
        yield World(
            client,
            clock,
            clients,
            organization_id,
            director,
            director_token,
            accountant,
            accountant_token,
        )


def test_representative_gives_the_company_consent_for_six_months(world: World) -> None:
    given = world.give(headers={"User-Agent": "Cabinet/1.0"})

    assert given == [
        {
            "type": "credit_bureau_company",
            "organization_id": str(world.organization_id),
            "given_by": str(world.director),
            "given_at": "2026-10-21T12:00:00Z",
            "valid_until": "2027-04-21T12:00:00Z",
            "revoked_at": None,
            "revoked_by": None,
            "active": True,
            "text_version": "bki-ul-2026-10",
        }
    ]
    assert world.consents(world.accountant_token) == given
    consent = world.active()
    assert consent is not None
    assert consent.account_id == world.director
    assert consent.organization_id == world.organization_id


def test_company_consent_runs_out(world: World) -> None:
    world.give()

    world.clock.set(datetime(2027, 4, 21, 12, 0, tzinfo=UTC))

    assert world.active() is None
    assert world.consents()[0]["active"] is False


def test_another_representative_revokes_it(world: World) -> None:
    world.give()
    world.clock.advance(timedelta(days=1))

    world.revoke(world.accountant_token)
    world.revoke(world.accountant_token)

    [consent] = world.consents()
    assert consent["revoked_at"] == "2026-10-22T12:00:00Z"
    assert consent["revoked_by"] == str(world.accountant)
    assert world.active() is None


def test_company_consents_are_not_personal_ones(world: World) -> None:
    world.give()

    personal = world.client.get("/me/consents", headers=auth(world.director_token))

    assert personal.json() == []
    assert world.active(uuid4()) is None


def test_employee_may_see_but_not_give(world: World) -> None:
    world.clients.add_member(world.accountant, world.organization_id, "employee")

    response = world.client.post(
        world.url(),
        json={"types": ["credit_bureau_company"]},
        headers=auth(world.accountant_token),
    )
    revoke = world.client.delete(
        f"{world.url()}/credit_bureau_company", headers=auth(world.accountant_token)
    )

    assert response.status_code == 403
    assert revoke.status_code == 403
    assert world.consents(world.accountant_token) == []


def test_a_stranger_does_not_see_the_company(world: World) -> None:
    other = world.clients.add_organization(builders.organization_snapshot("vector")).id

    listed = world.client.get(world.url(other), headers=auth(world.director_token))
    given = world.client.post(
        world.url(other),
        json={"types": ["credit_bureau_company"]},
        headers=auth(world.director_token),
    )

    assert listed.status_code == 404
    assert given.status_code == 404
    assert world.active(other) is None


@pytest.mark.parametrize(
    "body",
    [{"types": []}, {"types": ["personal_data"]}, {"types": ["credit_bureau_personal"]}],
    ids=["empty", "personal_data", "personal_bureau"],
)
def test_only_company_types_are_given_for_a_company(world: World, body: dict[str, Any]) -> None:
    response = world.client.post(world.url(), json=body, headers=auth(world.director_token))
    assert response.status_code == 422


def test_company_type_cannot_be_given_for_oneself(world: World) -> None:
    response = world.client.post(
        "/me/consents",
        json={"types": ["credit_bureau_company"]},
        headers=auth(world.director_token),
    )
    assert response.status_code == 422
