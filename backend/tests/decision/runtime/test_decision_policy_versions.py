"""Версии кредитной политики: реестр (черновик → активная → архив, откат), активная политика
для предодобрения и ночного пакета, примерка на прошлых автоматических решениях."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import InvalidStatusTransitionError, ValidationError
from src.modules.decision.application.policy_versions import ActivePolicyProvider, PolicyVersions
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.infrastructure.config_loader import CreditPolicyDocuments
from src.modules.decision.infrastructure.models import (
    DecisionPolicyVersionRecord,
    DecisionResultRecord,
)
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyPolicyVersionRepository,
)
from tests.decision.runtime.decision_runtime_world import (
    KEY_RATE,
    Sessions,
    make_decision,
    manual_command,
    record_manual,
)
from tests.decision.runtime.test_decision_runtime_pre_approval import _refresh, _World
from tests.decision.unit.decision_world import NOW, build_world

_NOW = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
_ADMIN = uuid4()
_BUILTIN = "policy_v10"

Edit = Callable[[dict[str, Any]], None]


def _versions(session: Any) -> PolicyVersions:
    return PolicyVersions(
        SqlAlchemyPolicyVersionRepository(session), CreditPolicyDocuments(), FrozenClock(_NOW)
    )


def _stop_okved(*classes: str) -> Edit:
    """Отказ по ОКВЭД ещё и для этих классов (у «Ромашки» — 56, общепит)."""

    def edit(body: dict[str, Any]) -> None:
        body["stop_factors"]["okved_classes"] = [*body["stop_factors"]["okved_classes"], *classes]

    return edit


def _stop_active(body: dict[str, Any]) -> None:
    """Стоп-фактор на действующую компанию: предодобрения нет ни у кого."""
    body["stop_factors"]["registry_statuses"]["active"] = "STOP_LIQUIDATION"


async def _draft(sessions: Sessions, based_on: str = _BUILTIN, edit: Edit | None = None) -> str:
    async with sessions() as session:
        versions = _versions(session)
        draft = await versions.create_draft(based_on, "проба", _ADMIN)
        if edit is not None:
            body = draft.body
            edit(body)
            await versions.update_draft(draft.version, body, None)
        await session.commit()
    return draft.version


async def _activate(sessions: Sessions, version: str) -> None:
    async with sessions() as session:
        await _versions(session).activate(version, _ADMIN)
        await session.commit()


async def _statuses(sessions: Sessions) -> dict[str, str]:
    async with sessions() as session:
        return {v.version: v.status for v in await _versions(session).list_all()}


async def _active(sessions: Sessions, provider: ActivePolicyProvider) -> CreditPolicy:
    async with sessions() as session:
        return await provider.active(SqlAlchemyPolicyVersionRepository(session))


async def test_builtin_is_in_force_without_versions(session_factory: Sessions) -> None:
    async with session_factory() as session:
        [builtin] = await _versions(session).list_all()
    policy = await _active(session_factory, ActivePolicyProvider(CreditPolicyDocuments()))

    assert (builtin.version, builtin.status, builtin.builtin) == (_BUILTIN, "active", True)
    assert builtin.body["version"] == _BUILTIN
    assert policy.version == _BUILTIN


async def test_draft_is_a_copy_under_the_next_number(session_factory: Sessions) -> None:
    first = await _draft(session_factory)
    second = await _draft(session_factory)
    third = await _draft(session_factory, based_on=first)

    assert (first, second, third) == ("policy_v10.1", "policy_v10.2", "policy_v10.3")
    async with session_factory() as session:
        draft = await _versions(session).get(third)
        builtin = await _versions(session).get(_BUILTIN)
    assert (draft.status, draft.based_on, draft.created_by) == ("draft", first, _ADMIN)
    # Код версии внутри документа — всегда код самой версии: он пишется в решения.
    assert draft.body["version"] == third
    assert {**draft.body, "version": _BUILTIN} == builtin.body


async def test_activation_archives_the_previous_and_rolls_back(session_factory: Sessions) -> None:
    first = await _draft(session_factory, edit=_stop_okved("56"))
    await _activate(session_factory, first)
    assert await _statuses(session_factory) == {_BUILTIN: "archived", first: "active"}

    second = await _draft(session_factory, edit=_stop_okved("41"))
    await _activate(session_factory, second)
    assert await _statuses(session_factory) == {
        _BUILTIN: "archived",
        first: "archived",
        second: "active",
    }

    # Откат на архивную версию.
    await _activate(session_factory, first)
    assert await _statuses(session_factory) == {
        _BUILTIN: "archived",
        first: "active",
        second: "archived",
    }
    async with session_factory() as session:
        rolled_back = await _versions(session).get(first)
    assert rolled_back.activated_by == _ADMIN and rolled_back.activated_at is not None

    # Вернуть встроенную: активная версия из БД уходит в архив.
    await _activate(session_factory, _BUILTIN)
    assert await _statuses(session_factory) == {
        _BUILTIN: "active",
        first: "archived",
        second: "archived",
    }
    with pytest.raises(InvalidStatusTransitionError):
        await _activate(session_factory, _BUILTIN)


async def test_only_a_draft_is_changed_or_deleted(session_factory: Sessions) -> None:
    active = await _draft(session_factory)
    await _activate(session_factory, active)
    draft = await _draft(session_factory)

    async with session_factory() as session:
        versions = _versions(session)
        body = (await versions.get(active)).body
        for version in (active, _BUILTIN):
            with pytest.raises(InvalidStatusTransitionError):
                await versions.update_draft(version, body, None)
            with pytest.raises(InvalidStatusTransitionError):
                await versions.delete_draft(version)
        with pytest.raises(InvalidStatusTransitionError):
            await versions.activate(active, _ADMIN)  # уже активна
        await versions.delete_draft(draft)
        await session.commit()

    assert set(await _statuses(session_factory)) == {_BUILTIN, active}


async def test_broken_document_lists_every_problem(session_factory: Sessions) -> None:
    draft = await _draft(session_factory)
    async with session_factory() as session:
        versions = _versions(session)
        body = (await versions.get(draft)).body
        body["routing"]["flags"]["mass_address"] = "ROUTE_NOT_EXPLAINED"  # кода нет в текстах
        body["strategy"]["guarantee"]["grades"] = ["F", "Z"]  # грейд вне шкалы
        del body["strategy"]["two_models"]["matrix"]["yellow"]["red"]  # дырка в матрице
        with pytest.raises(ValidationError) as error:
            await versions.update_draft(draft, body, None)

    assert error.value.status_code == 422
    errors = {e["path"]: e["message"] for e in error.value.details["errors"]}  # type: ignore[index]
    assert errors == {
        "routing.flags.mass_address": "нет текста для кода причины ROUTE_NOT_EXPLAINED",
        "strategy.guarantee.grades": "грейды вне шкалы: ['Z']",
        "strategy.two_models.matrix": "по строке и столбцу на каждую зону "
        "['green', 'red', 'yellow']",
    }


async def test_one_active_version_is_kept_by_the_database(session_factory: Sessions) -> None:
    def record(version: str) -> DecisionPolicyVersionRecord:
        return DecisionPolicyVersionRecord(
            version=version,
            status="active",
            body={},
            created_by=_ADMIN,
            created_at=_NOW,
            updated_at=_NOW,
        )

    async with session_factory() as session:
        session.add_all([record("policy_v10.1"), record("policy_v10.2")])
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_provider_takes_the_active_version_and_keeps_it(session_factory: Sessions) -> None:
    provider = ActivePolicyProvider(CreditPolicyDocuments())
    version = await _draft(session_factory, edit=_stop_okved("56"))
    await _activate(session_factory, version)

    policy = await _active(session_factory, provider)
    again = await _active(session_factory, provider)

    assert policy.version == version
    assert again is policy  # собрана один раз на процесс
    assert "56" in policy.config.stop_okved_classes

    await _activate(session_factory, _BUILTIN)
    assert (await _active(session_factory, provider)).version == _BUILTIN


async def test_nightly_refresh_takes_the_active_version(session_factory: Sessions) -> None:
    """Пакет берёт политику на проходе, а не при создании: активировали версию со стоп-фактором
    на действующую компанию — продлевать нечего, предложения сняты."""
    world = _World("romashka")
    refresh = _refresh(session_factory, world)
    await world.recalculate(session_factory, NOW - timedelta(days=28))
    assert await world.valid_until(session_factory)
    await _activate(session_factory, await _draft(session_factory, edit=_stop_active))

    assert await refresh.execute(within_days=3) == 1

    assert await world.valid_until(session_factory) == set()


# --- примерка -------------------------------------------------------------------------------


async def test_preview_decides_the_latest_automatic_decisions_again(
    session_factory: Sessions,
) -> None:
    romashka = await build_world("s1_romashka", acts_for_itself=True)
    # Повторное автоматическое решение той же заявки: в примерку идёт только последнее, ручное
    # решение после него — не берём.
    await make_decision(session_factory, romashka)
    await make_decision(session_factory, romashka)
    await record_manual(
        session_factory, romashka, manual_command(romashka, "APPROVE", amount="2000000")
    )
    # Заявка, которой у соседей уже нет: вход не собрать — пропущена.
    gone = await build_world("s3_vector")
    await make_decision(session_factory, gone)
    version = await _draft(session_factory, edit=_stop_okved("56"))

    async with session_factory() as session:
        before = (await session.scalars(select(func.count(DecisionResultRecord.id)))).one()
        preview = await _versions(session).preview(
            version, 50, SqlAlchemyDecisionRepository(session), romashka.builder, KEY_RATE
        )
        after = (await session.scalars(select(func.count(DecisionResultRecord.id)))).one()

    assert before == after == 4  # примерка ничего не пишет
    assert preview.skipped == 1
    [item] = preview.items
    assert item.application_id == romashka.application_id
    assert (item.before.outcome, item.before.policy_version) == ("APPROVE", _BUILTIN)
    assert (item.after.outcome, item.after.policy_version) == ("REJECT", version)
    assert item.after.reason_codes == ("STOP_FORBIDDEN_OKVED",)
    assert (preview.changed, preview.outcome_changed) == (1, 1)
    assert [(s.from_outcome, s.to_outcome, s.count) for s in preview.transitions] == [
        ("APPROVE", "REJECT", 1)
    ]

    async with session_factory() as session:
        same = await _versions(session).preview(
            _BUILTIN, 50, SqlAlchemyDecisionRepository(session), romashka.builder, KEY_RATE
        )
    [unchanged] = same.items
    assert (same.changed, same.outcome_changed) == (0, 0)
    assert unchanged.after.reason_codes == unchanged.before.reason_codes
    assert unchanged.after.policy_version == _BUILTIN
