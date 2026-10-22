"""MakeDecision: команда → решение в базе → ответ `DecisionMade` (S-1…S-7 на фейковых соседях)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.messaging.contracts.decision import DecisionMade
from tests.decision.runtime.decision_runtime_world import (
    KEY_RATE,
    Sessions,
    by_command,
    decision,
    make_decision,
    stored_count,
)
from tests.decision.unit.decision_world import NOW, build_world


async def test_s1_romashka_is_approved_as_requested(session_factory: Sessions) -> None:
    world = await build_world("s1_romashka")
    event_id = uuid4()

    outbox = await make_decision(session_factory, world, event_id)

    [staged] = outbox.messages
    assert staged.key == str(world.application_id)
    assert staged.correlation_id == world.application_id
    assert staged.causation_id == event_id
    made = staged.message
    assert isinstance(made, DecisionMade)
    assert made.outcome == "APPROVE"
    assert made.decided_by == "auto"
    assert made.client_explanation == "Заявка одобрена на запрошенных условиях."
    assert made.alternative_product_code is None and made.requested_info is None
    offer = made.offer
    assert offer is not None
    assert offer.kind == "as_requested"
    assert (offer.amount, offer.term_months, offer.rate) == (
        Decimal(3_000_000),
        24,
        Decimal("23.50"),
    )
    assert offer.schedule_type == "annuity"
    expected = world.products.calculate_payment(Decimal(3_000_000), 24, Decimal("23.50"), "annuity")
    assert offer.monthly_payment == expected.monthly_payment == Decimal("157865.62")
    assert offer.expires_at == NOW + timedelta(days=7)

    stored = await decision(session_factory, world.application_id)
    assert stored is not None and stored.id == made.decision_id
    assert stored.key_rate == KEY_RATE and stored.policy_version == "policy_v2"
    assert stored.decided_by_type == "auto" and stored.override_of is None
    assert stored.terms is not None and stored.terms.monthly_payment == offer.monthly_payment
    assert stored.limits.by_revenue is not None and stored.limits.by_capacity is not None
    assert any(hit.rule == "outcome.approve" and hit.matched for hit in stored.rule_trace)


@pytest.mark.parametrize(
    ("name", "outcome", "with_offer"),
    [
        ("s2_ivanov", "COUNTER_OFFER", True),
        ("s3_vector", "MANUAL_REVIEW", False),
        ("s4_zakat", "REJECT", False),
        ("s5a_progress", "REQUEST_INFO", False),
        ("s5b_progress", "MANUAL_REVIEW", False),
        ("s6_sboy", "MANUAL_REVIEW", False),
        ("s7_romashka_mortgage", "MANUAL_REVIEW", False),
    ],
)
async def test_outcome_reaches_the_reply(
    session_factory: Sessions, name: str, outcome: str, with_offer: bool
) -> None:
    world = await build_world(name)

    outbox = await make_decision(session_factory, world)

    [made] = outbox.of_type(DecisionMade)
    assert made.outcome == outcome
    assert (made.offer is not None) is with_offer
    stored = await decision(session_factory, world.application_id)
    assert stored is not None and stored.outcome == outcome and stored.id == made.decision_id


async def test_s2_counter_offer_names_the_overdraft(session_factory: Sessions) -> None:
    world = await build_world("s2_ivanov")

    [made] = (await make_decision(session_factory, world)).of_type(DecisionMade)

    assert made.offer is not None and made.offer.kind == "counter"
    assert Decimal(300_000) <= made.offer.amount < Decimal(5_000_000)
    assert made.alternative_product_code == "OVERDRAFT"
    assert any("кассового разрыва" in condition for condition in made.offer.conditions)
    assert made.improvement_hints


async def test_s5a_requests_the_bank_statement(session_factory: Sessions) -> None:
    world = await build_world("s5a_progress")

    [made] = (await make_decision(session_factory, world)).of_type(DecisionMade)

    assert made.requested_info is not None
    assert made.requested_info.documents == ["bank_statement"]
    assert "выписк" in made.requested_info.comment
    stored = await decision(session_factory, world.application_id)
    assert stored is not None and stored.reason_codes == ("INFO_REVENUE_NOT_CONFIRMED",)


async def test_repeated_command_returns_the_same_decision(session_factory: Sessions) -> None:
    world = await build_world("s1_romashka")
    event_id = uuid4()

    first = await make_decision(session_factory, world, event_id)
    again = await make_decision(session_factory, world, event_id)

    [made] = first.of_type(DecisionMade)
    [repeated] = again.of_type(DecisionMade)
    assert repeated == made
    assert again.messages[0].causation_id == event_id
    assert await stored_count(session_factory, world.application_id) == 1


async def test_new_command_adds_a_decision_and_it_becomes_the_latest(
    session_factory: Sessions,
) -> None:
    world = await build_world("s5a_progress")
    first_event, second_event = uuid4(), uuid4()
    await make_decision(session_factory, world, first_event)

    # Тот же замороженный момент: последним всё равно считается второе решение.
    [second] = (await make_decision(session_factory, world, second_event)).of_type(DecisionMade)

    assert await stored_count(session_factory, world.application_id) == 2
    latest = await decision(session_factory, world.application_id)
    assert latest is not None and latest.id == second.decision_id
    first = await by_command(session_factory, first_event)
    assert first is not None and first.id != second.decision_id
