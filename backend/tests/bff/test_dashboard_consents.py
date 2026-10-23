"""The consents asked for before an application, on the dashboard: which are given for
the person and the company, which are missing and what each lets the bank do."""

from collections.abc import Callable
from datetime import datetime, timedelta

from src.modules.identity.facade import IdentityFacade
from tests.bff.conftest import World
from tests.fakes.builders import NOW


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def test_dashboard_shows_what_is_missing(world: World) -> None:
    body = world.get("/bff/dashboard", world.as_client(world.accountant)).json()

    assert [(c["type"], c["scope"], c["required"], c["given"]) for c in body["consents"]] == [
        ("personal_data", "account", True, False),
        ("credit_bureau_company", "organization", True, False),
    ]
    assert all(c["title"] and c["purpose"] for c in body["consents"])
    assert body["degraded"] == []


def test_company_consent_given_by_another_representative_counts(world: World) -> None:
    given_at = NOW - timedelta(days=2)
    world.identity.give_consent(world.accountant, "personal_data", given_at)
    world.identity.give_organization_consent(
        world.romashka.id, world.director, given_at, valid_until=given_at + timedelta(days=182)
    )

    body = world.get("/bff/dashboard", world.as_client(world.accountant)).json()

    by_type = {c["type"]: c for c in body["consents"]}
    assert by_type["personal_data"]["given"] is True
    assert by_type["personal_data"]["valid_until"] is None
    company = by_type["credit_bureau_company"]
    assert company["given"] is True
    assert company["given_at"] == _iso(given_at)
    assert company["valid_until"] == _iso(given_at + timedelta(days=182))


def test_the_head_also_sees_their_own_credit_history_consent(world: World) -> None:
    world.clients.registry_heads[world.romashka.id] = world.director
    world.identity.give_consent(world.director, "credit_bureau_personal", NOW)

    body = world.get("/bff/dashboard", world.as_client(world.director)).json()

    assert [(c["type"], c["required"], c["given"]) for c in body["consents"]] == [
        ("personal_data", True, False),
        ("credit_bureau_company", True, False),
        ("credit_bureau_personal", False, True),
    ]


def test_consents_of_another_company_do_not_count(world: World) -> None:
    world.identity.give_organization_consent(world.vector.id, world.petrov, NOW)

    body = world.get("/bff/dashboard", world.as_client(world.accountant)).json()

    assert {c["type"]: c["given"] for c in body["consents"]}["credit_bureau_company"] is False


def test_dashboard_without_identity_is_served(make_world: Callable[..., World]) -> None:
    world = make_world(skip=(IdentityFacade,))

    response = world.get("/bff/dashboard", world.as_client(world.accountant))

    assert response.status_code == 200, response.text
    assert response.json()["consents"] == []
    assert response.json()["degraded"] == ["consents"]
