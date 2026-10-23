"""Consents given in the profile before the application (#152): the person's
personal_data and the company's credit_bureau_company. A draft takes the ones it lacks
when it is created and when it is submitted; the application keeps them for audit."""

from datetime import timedelta
from typing import Any

from tests.applications.api.conftest import World


def _iso(world: World, days_ago: int) -> str:
    return (world.clock.now() - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def _give_in_profile(world: World) -> None:
    now = world.clock.now()
    world.identity.give_consent(world.director, "personal_data", now - timedelta(days=30))
    world.identity.give_organization_consent(
        world.romashka, world.accountant, now - timedelta(days=2)
    )


def _without_consents(world: World) -> dict[str, Any]:
    """A draft that has everything but the consents."""
    application = world.create()
    world.upload(application)
    response = world.client.patch(
        f"/applications/{application['id']}",
        json={
            "version": world.client.get(
                f"/applications/{application['id']}", headers=world.headers(world.director)
            ).json()["version"],
            "request": {"amount": "3000000", "term_months": 24, "purpose": "working_capital"},
        },
        headers=world.headers(world.director),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_new_draft_takes_the_consents_from_the_profile(world: World) -> None:
    _give_in_profile(world)

    application = world.create()

    assert application["consents"] == {
        "personal_data_at": _iso(world, 30),
        "credit_bureau_at": _iso(world, 2),
        "automated_decision_at": None,
        "personal_data_source": "profile",
        "credit_bureau_source": "profile",
    }


def test_consents_given_after_the_draft_are_taken_on_submission(world: World) -> None:
    application = _without_consents(world)
    assert application["consents"]["credit_bureau_source"] is None
    _give_in_profile(world)

    submitted = world.submit(application)

    assert submitted["status"] == "submitted"
    assert submitted["consents"]["personal_data_source"] == "profile"
    assert submitted["consents"]["credit_bureau_at"] == _iso(world, 2)


def test_without_any_consent_the_application_is_not_submitted(world: World) -> None:
    application = _without_consents(world)
    # A company consent alone is not enough: the personal one is missing.
    world.identity.give_organization_consent(world.romashka, world.director, world.clock.now())

    response = world.client.post(
        f"/applications/{application['id']}/submit", headers=world.headers(world.director)
    )

    assert response.status_code == 422, response.text
    assert "consents.personal_data" in response.text
    assert "consents.credit_bureau" not in response.text


def test_a_checkbox_in_the_draft_still_works(world: World) -> None:
    world.identity.give_organization_consent(
        world.romashka, world.accountant, world.clock.now() - timedelta(days=2)
    )

    ready = world.ready()

    assert ready["consents"]["personal_data_source"] == "application"
    # The company consent was taken when the draft was created and stays.
    assert ready["consents"]["credit_bureau_source"] == "profile"
    submitted = world.submit(ready)
    assert submitted["consents"]["personal_data_source"] == "application"


def test_another_company_consent_does_not_count(world: World) -> None:
    world.identity.give_organization_consent(world.vector, world.petrov, world.clock.now())

    application = world.create()

    assert application["consents"]["credit_bureau_at"] is None
