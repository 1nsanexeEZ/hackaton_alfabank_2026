"""The head's own consent to the request of their credit history: on the card
for everyone in the company, on the dashboard as a to-do for the head only."""

from collections.abc import Callable
from datetime import timedelta

from src.modules.identity.facade import IdentityFacade
from tests.bff.conftest import World
from tests.fakes.builders import NOW


def test_card_shows_the_consent_the_head_gave(world: World) -> None:
    world.clients.registry_heads[world.romashka.id] = world.director
    world.identity.give_consent(world.director, "credit_bureau_personal", NOW - timedelta(days=1))
    card = world.add_application(status="in_review")

    body = world.get(f"/bff/applications/{card.id}", world.as_client(world.accountant)).json()

    assert body["consents"]["head_credit_bureau"] == {
        "required": True,
        "given": True,
        "given_at": (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "head_name": world.romashka.head_name,
    }
    assert body["degraded"] == []


def test_card_of_a_company_whose_head_has_no_account(world: World) -> None:
    card = world.add_application(status="in_review")

    body = world.get(f"/bff/applications/{card.id}", world.as_client(world.director)).json()

    assert body["consents"]["head_credit_bureau"] == {
        "required": True,
        "given": False,
        "given_at": None,
        "head_name": world.romashka.head_name,
    }


def test_card_without_identity_is_served(make_world: Callable[..., World]) -> None:
    world = make_world(skip=(IdentityFacade,))
    world.clients.registry_heads[world.romashka.id] = world.director
    card = world.add_application(status="in_review")

    response = world.get(f"/bff/applications/{card.id}", world.as_client(world.director))

    assert response.status_code == 200, response.text
    assert response.json()["consents"] == {"head_credit_bureau": None}
    assert response.json()["degraded"] == ["head_consent"]


def test_dashboard_asks_the_head_for_the_consent(world: World) -> None:
    world.clients.registry_heads[world.romashka.id] = world.director
    review = world.add_application(status="in_review", number="КР-1")

    head = world.get("/bff/dashboard", world.as_client(world.director)).json()
    accountant = world.get("/bff/dashboard", world.as_client(world.accountant)).json()

    assert [(t["application_id"], t["kind"]) for t in head["todo"]] == [
        (str(review.id), "consent_required")
    ]
    assert "КР-1" in head["todo"][0]["title"]
    assert accountant["todo"] == []


def test_dashboard_does_not_ask_once_the_consent_is_given(world: World) -> None:
    world.clients.registry_heads[world.romashka.id] = world.director
    world.identity.give_consent(world.director, "credit_bureau_personal", NOW)
    world.add_application(status="in_review")

    body = world.get("/bff/dashboard", world.as_client(world.director)).json()

    assert body["todo"] == []


def test_dashboard_does_not_ask_for_a_draft_or_after_the_decision(world: World) -> None:
    world.clients.registry_heads[world.romashka.id] = world.director
    world.add_application(status="draft")
    world.add_application(status="signing", number="КР-2")

    body = world.get("/bff/dashboard", world.as_client(world.director)).json()

    assert [t["kind"] for t in body["todo"]] == ["signing"]
