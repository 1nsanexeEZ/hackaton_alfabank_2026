"""CheckStopFactors: стоп-факторы до скоринга (policy_v7).

Нет стоп-фактора — `StopFactorsPassed`, решения в базе нет. Есть — решение без модели в базе и
обычный `DecisionMade`; повтор команды — то же решение.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from src.core.messaging.contracts.decision import DecisionMade, StopFactorsPassed
from tests.decision.runtime.decision_runtime_world import (
    Sessions,
    by_command,
    check_stop_factors,
    decision,
    stored_count,
)
from tests.decision.unit.decision_world import DecisionWorld, build_world


def liquidate(world: DecisionWorld) -> None:
    snapshot = world.enrichment.snapshots[world.application_id]
    assert snapshot.egrul is not None
    world.enrichment.add_snapshot(
        replace(snapshot, egrul=replace(snapshot.egrul, status="liquidated"))
    )


async def test_clean_company_goes_on_to_scoring(session_factory: Sessions) -> None:
    world = await build_world("s1_romashka")
    event_id = uuid4()

    outbox = await check_stop_factors(session_factory, world, event_id)

    [staged] = outbox.messages
    assert isinstance(staged.message, StopFactorsPassed)
    assert staged.message.application_id == world.application_id
    assert staged.causation_id == event_id and staged.key == str(world.application_id)
    assert await stored_count(session_factory, world.application_id) == 0


async def test_stop_factor_is_a_decision_without_the_model(session_factory: Sessions) -> None:
    world = await build_world("s1_romashka")
    liquidate(world)
    event_id = uuid4()

    outbox = await check_stop_factors(session_factory, world, event_id)

    [staged] = outbox.messages
    made = staged.message
    assert isinstance(made, DecisionMade)
    assert made.outcome == "REJECT" and made.offer is None and made.decided_by == "auto"
    assert staged.causation_id == event_id
    stored = await decision(session_factory, world.application_id)
    assert stored is not None and stored.id == made.decision_id
    assert stored.policy_version == "policy_v9"
    assert stored.reason_codes == ("STOP_LIQUIDATION",)
    assert not any(hit.rule.startswith("strategy.") for hit in stored.rule_trace)
    record = await by_command(session_factory, event_id)
    assert record is not None and record.inputs.scoring_result_id is None

    again = await check_stop_factors(session_factory, world, event_id)
    [repeated] = again.messages
    assert isinstance(repeated.message, DecisionMade)
    assert repeated.message.decision_id == made.decision_id
    assert await stored_count(session_factory, world.application_id) == 1
