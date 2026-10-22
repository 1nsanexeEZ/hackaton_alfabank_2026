"""Client screens never carry the score, scoring factors, the rule trace,
reason codes or credit bureau data — even when every neighbour has them."""

from typing import Any

import httpx

from src.applications.facade import ApplicationCardDTO
from tests.bff import factories
from tests.bff.conftest import World

FORBIDDEN_KEYS = {
    "score",
    "grade",
    "risk_grade",
    "factors",
    "flags",
    "rule_trace",
    "reason_codes",
    "limits",
    "bki",
    "credit_history",
    "obligations",
    "egrul",
    "fns",
    "enrichment",
    "scoring",
    "basis",
    "policy_version",
    "decided_by_id",
    "details",
}


def keys_of(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_of(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_of(v)}
    return set()


def assert_client_safe(response: httpx.Response) -> None:
    assert response.status_code == 200, response.text
    assert not keys_of(response.json()) & FORBIDDEN_KEYS
    for marker in factories.INTERNAL_MARKERS:
        assert marker not in response.text


def everything_known_about(world: World, card: ApplicationCardDTO) -> None:
    world.enrichment.add_snapshot(factories.enrichment_snapshot(card.id, card.organization_id))
    world.scoring.add_result(factories.scoring_result(card.id))
    world.decision.add_decision(factories.decision(card.id))
    world.decision.set_pre_approved(card.organization_id, [factories.pre_approved()])
    world.projector.add_timeline_entry(factories.timeline_entry(card.id, "Заявка принята"))
    world.projector.add_timeline_entry(
        factories.timeline_entry(
            card.id, factories.BANK_TIMELINE_TITLE, "bank", "decision", 1, {"score": 612}
        )
    )
    # A client entry with internal details: the client gets only time, kind, title.
    world.projector.add_timeline_entry(
        factories.timeline_entry(
            card.id, "Оцениваем заявку", minutes=2, details={"rule": factories.RULE_NAME}
        )
    )
    world.process.add_view(factories.process_view(card.id))


def test_client_screens_carry_no_internal_data(world: World) -> None:
    card = world.add_application(
        status="offer_ready",
        offer=factories.offer(),
        decision_summary=factories.decision_summary(),
    )
    everything_known_about(world, card)
    headers = world.as_client(world.director)
    org = world.romashka.id

    assert_client_safe(world.get("/bff/dashboard", headers))
    assert_client_safe(world.get("/bff/applications", headers, organization_id=org))
    assert_client_safe(world.get(f"/bff/applications/{card.id}", headers))
    assert_client_safe(
        world.get(
            "/bff/products/recommend",
            headers,
            organization_id=org,
            purpose="working_capital",
            amount="1000000",
            term_months=12,
        )
    )


def test_client_card_shows_the_decision_without_internals(world: World) -> None:
    card = world.add_application(status="offer_ready", offer=factories.offer())
    everything_known_about(world, card)

    body = world.get(f"/bff/applications/{card.id}", world.as_client(world.director)).json()

    assert body["decision"]["outcome"] == "APPROVE"
    assert body["decision"]["client_explanation"] == "Одобрено на запрошенных условиях"
    assert body["decision"]["improvement_hints"] == ["Подключите эквайринг"]
    assert [e["title"] for e in body["timeline"]] == ["Заявка принята", "Оцениваем заявку"]


def test_the_bank_sees_the_internals(world: World) -> None:
    card = world.add_application(status="in_review")
    everything_known_about(world, card)

    response = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter())

    assert response.status_code == 200
    for marker in (
        factories.REASON_CODE,
        factories.RULE_NAME,
        factories.FACTOR_CODE,
        factories.BKI_CREDITOR,
        factories.BANK_TIMELINE_TITLE,
    ):
        assert marker in response.text
