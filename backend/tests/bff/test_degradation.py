"""Decision, process and scoring are wired by their owners later: until then
(and while a source is down) their blocks are empty and named in `degraded`,
the screen itself is served."""

from collections.abc import Callable
from uuid import UUID

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.decision.facade import DecisionFacade
from src.modules.notifications.facade import NotificationsFacade
from src.modules.process.facade import ProcessFacade
from src.modules.projector.facade import TimelineEntryDTO
from src.modules.scoring.facade import ScoringFacade
from tests.bff import factories
from tests.bff.conftest import World


def test_underwriter_card_without_decision_process_and_scoring(
    make_world: Callable[..., World],
) -> None:
    world = make_world(skip=(DecisionFacade, ProcessFacade, ScoringFacade))
    card = world.add_application(status="in_review")
    world.enrichment.add_snapshot(factories.enrichment_snapshot(card.id, card.organization_id))

    response = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application"]["id"] == str(card.id)
    assert body["enrichment"]["cashflow"]["gap_detected"] is True
    assert body["scoring"] is None
    assert body["decision"] is None
    assert body["process"] is None
    assert body["task"] is None
    assert sorted(body["degraded"]) == ["decision", "process", "scoring", "task"]


def test_client_card_falls_back_to_the_decision_summary(
    make_world: Callable[..., World],
) -> None:
    world = make_world(skip=(DecisionFacade,))
    card = world.add_application(
        status="offer_ready",
        offer=factories.offer(),
        decision_summary=factories.decision_summary(),
    )

    response = world.get(f"/bff/applications/{card.id}", world.as_client(world.director))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] == ["decision"]
    assert body["decision"]["outcome"] == "APPROVE"
    assert body["decision"]["terms"] is None
    assert body["client_status"] == "approved"


def test_dashboard_without_decision_and_notifications(make_world: Callable[..., World]) -> None:
    world = make_world(skip=(DecisionFacade, NotificationsFacade))
    world.add_application(status="info_requested")

    response = world.get("/bff/dashboard", world.as_client(world.director))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pre_approved"] == []
    assert body["feed"] == {"unread": 0, "items": []}
    assert body["news"] == []
    assert len(body["todo"]) == 1
    assert body["degraded"] == ["pre_approved", "feed", "news"]


def test_a_source_that_is_down_degrades_its_block(world: World) -> None:
    card = world.add_application(status="in_review")

    async def broken(application_id: UUID, audience: str) -> list[TimelineEntryDTO]:
        raise InfrastructureError("projector database is unavailable")

    world.projector.get_timeline = broken  # type: ignore[method-assign,assignment]

    client = world.get(f"/bff/applications/{card.id}", world.as_client(world.director))
    bank = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter())

    assert client.status_code == 200
    assert client.json()["timeline"] == []
    assert client.json()["degraded"] == ["timeline"]
    assert bank.status_code == 200
    assert bank.json()["degraded"] == ["timeline"]
