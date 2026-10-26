"""Фасад decision: банку — всё, клиенту — без внутренних кодов, трассы и комментария."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from uuid import uuid4

from src.core.domain.clock import FrozenClock
from src.modules.decision.facade import ClientDecisionDTO
from src.modules.decision.infrastructure.config_loader import default_policy
from src.modules.decision.infrastructure.facade_impl import DecisionFacadeImpl
from tests.decision.runtime.decision_runtime_world import (
    KEY_RATE,
    Sessions,
    client_view,
    decision,
    make_decision,
    manual_command,
    record_manual,
)
from tests.decision.unit.decision_world import NOW, build_world

_INTERNAL_FIELDS = {"reason_codes", "rule_trace", "limits", "comment", "key_rate", "policy_version"}


async def test_bank_view_explains_the_decision(session_factory: Sessions) -> None:
    world = await build_world("s3_vector", acts_for_itself=True)
    await make_decision(session_factory, world)

    bank = await decision(session_factory, world.application_id)

    assert bank is not None
    assert bank.outcome == "MANUAL_REVIEW"
    assert "ROUTE_VERIFICATION_MISMATCH" in bank.reason_codes
    assert any(h.rule == "route.verification_mismatch" and h.matched for h in bank.rule_trace)
    assert bank.key_rate == KEY_RATE and bank.policy_version == default_policy().version
    assert bank.limits.by_revenue is not None


async def test_client_view_has_no_internal_data(session_factory: Sessions) -> None:
    world = await build_world("s3_vector", acts_for_itself=True)
    await make_decision(session_factory, world)
    comment = "Внутренняя пометка: проверить связь с ООО «Рога»"
    await record_manual(
        session_factory,
        world,
        manual_command(world, "COUNTER_OFFER", amount="8000000", comment=comment),
    )
    bank = await decision(session_factory, world.application_id)
    assert bank is not None

    view = await client_view(session_factory, world.application_id)

    assert view is not None
    assert {f.name for f in fields(ClientDecisionDTO)}.isdisjoint(_INTERNAL_FIELDS)
    dumped = json.dumps(asdict(view), default=str, ensure_ascii=False)
    for code in ("ROUTE_", "STOP_", "LIMIT_BY_", "INFO_"):
        assert code not in dumped
    for hit in bank.rule_trace:
        assert hit.rule not in dumped
    assert comment not in dumped
    assert view.outcome == bank.outcome and view.terms == bank.terms


async def test_client_view_of_the_automatic_decision(session_factory: Sessions) -> None:
    world = await build_world("s4_zakat", acts_for_itself=True)
    await make_decision(session_factory, world)

    view = await client_view(session_factory, world.application_id)

    assert view is not None and view.outcome == "REJECT"
    dumped = json.dumps(asdict(view), default=str, ensure_ascii=False)
    assert "STOP_" not in dumped and "stop." not in dumped
    assert "ликвидации" in view.client_explanation


async def test_nothing_decided_yet(session_factory: Sessions) -> None:
    async with session_factory() as session:
        facade = DecisionFacadeImpl(session, FrozenClock(NOW))
        assert await facade.get_decision(uuid4()) is None
        assert await facade.get_client_view(uuid4()) is None
        assert await facade.get_pre_approved(uuid4()) == []


async def test_decisions_of_a_list_are_the_latest_of_each(session_factory: Sessions) -> None:
    """Ручное решение поверх автоматического — в пакете последнее, как у `get_decision`."""
    world = await build_world("s3_vector", acts_for_itself=True)
    other = await build_world("s1_romashka")
    await make_decision(session_factory, world)
    await make_decision(session_factory, other)
    await record_manual(session_factory, world, manual_command(world, "APPROVE", amount="2000000"))

    async with session_factory() as session:
        facade = DecisionFacadeImpl(session, FrozenClock(NOW))
        found = await facade.get_decisions([world.application_id, other.application_id, uuid4()])
        assert await facade.get_decisions([]) == {}

    assert set(found) == {world.application_id, other.application_id}
    assert found[world.application_id].decided_by_type == "underwriter"
    assert found[world.application_id] == await decision(session_factory, world.application_id)
