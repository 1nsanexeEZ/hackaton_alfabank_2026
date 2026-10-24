"""Ручки версий кредитной политики: чтение и примерка — `scoring.read`, ведение —
`scoring.update`. Активированная версия решает команды процесса.

Соседи — фейки мира S-1 («Ромашка», ОКВЭД 56): примерке и `MakeDecision` есть из чего собрать
вход."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.decision import MakeDecision
from src.main import create_app
from src.modules.applications.facade import ApplicationsFacade
from src.modules.decision.facade import DecisionFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade
from tests.decision.runtime.test_decision_runtime_app import App
from tests.decision.unit.decision_world import NOW, build_world
from tests.fakes import install
from tests.helpers import bearer, create_schema, token_for

POLICIES = "/decision/policies"
BUILTIN = "policy_v10"


@pytest.fixture
def app(settings: Settings) -> Iterator[App]:
    world = asyncio.run(build_world("s1_romashka", acts_for_itself=True))
    application = create_app(settings, clock=FrozenClock(NOW))
    install(application, ApplicationsFacade, world.applications)
    install(application, EnrichmentFacade, world.enrichment)
    install(application, ScoringFacade, world.scoring)
    install(application, ProductsFacade, world.products)
    create_schema(settings.database_url)
    with TestClient(application) as client:
        yield App(client, world)


def _headers(app: App, *permissions: Permissions) -> dict[str, str]:
    return bearer(token_for(app.client.app, list(permissions)))  # type: ignore[arg-type]


def _admin(app: App) -> dict[str, str]:
    return _headers(app, Permissions.ADMIN)


def _reader(app: App) -> dict[str, str]:
    """Как у андеррайтера: читать и примерять, но не править."""
    return _headers(app, Permissions.SCORING_READ, Permissions.DECISIONS_READ)


def _statuses(app: App) -> dict[str, str]:
    versions = app.client.get(POLICIES, headers=_admin(app)).json()
    return {v["version"]: v["status"] for v in versions}


def _stop_okved_56(body: dict[str, Any]) -> dict[str, Any]:
    """Отказ по ОКВЭД ещё и для общепита — класса «Ромашки»."""
    body["stop_factors"]["okved_classes"] = [*body["stop_factors"]["okved_classes"], "56"]
    return body


def test_reader_sees_the_policies_but_does_not_keep_them(app: App) -> None:
    api, reader = app.client, _reader(app)

    versions = api.get(POLICIES, headers=reader)
    assert versions.status_code == 200, versions.text
    assert [(v["version"], v["status"], v["builtin"]) for v in versions.json()] == [
        (BUILTIN, "active", True)
    ]
    builtin = api.get(f"{POLICIES}/{BUILTIN}", headers=reader).json()
    assert builtin["body"]["version"] == BUILTIN
    assert {"stop_factors", "limits", "pricing", "routing", "strategy"} <= set(builtin["body"])

    catalog = api.get(f"{POLICIES}/catalog", headers=reader).json()
    assert catalog["builtin"] == BUILTIN
    assert catalog["pd_scale"][0] == "A"
    reasons = {r["code"]: r for r in catalog["reasons"]}
    assert reasons["STOP_FORBIDDEN_OKVED"]["text"]
    assert "okved_classes" in catalog["stop_factors"]
    assert {o["code"] for o in catalog["outcomes"]} >= {"APPROVE", "REJECT", "MANUAL_REVIEW"}

    for method, path, body in [
        ("POST", POLICIES, {"based_on": BUILTIN}),
        ("PUT", f"{POLICIES}/{BUILTIN}", {"body": builtin["body"]}),
        ("DELETE", f"{POLICIES}/{BUILTIN}", None),
        ("POST", f"{POLICIES}/{BUILTIN}/activate", None),
    ]:
        response = api.request(method, path, json=body, headers=reader)
        assert response.status_code == 403, path

    outsider = _headers(app, Permissions.DECISIONS_READ)
    assert api.get(POLICIES, headers=outsider).status_code == 403
    assert api.post(f"{POLICIES}/{BUILTIN}/preview", headers=outsider).status_code == 403
    assert api.get(POLICIES).status_code == 401


def test_admin_drafts_checks_activates_and_rolls_back(app: App) -> None:
    api, admin = app.client, _admin(app)

    created = api.post(
        POLICIES, json={"based_on": BUILTIN, "comment": "Без общепита"}, headers=admin
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert (draft["version"], draft["status"], draft["based_on"]) == (
        "policy_v10.1",
        "draft",
        BUILTIN,
    )
    assert api.post(POLICIES, json={"based_on": "policy_v99"}, headers=admin).status_code == 404

    # Код причины без текста для клиента — 422 со списком {path, message}.
    broken = draft["body"]
    broken["routing"]["flags"]["mass_address"] = "ROUTE_NOT_EXPLAINED"
    rejected = api.put(f"{POLICIES}/policy_v10.1", json={"body": broken}, headers=admin)
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["code"] == "validation_error"
    assert rejected.json()["details"]["errors"] == [
        {
            "path": "routing.flags.mass_address",
            "message": "нет текста для кода причины ROUTE_NOT_EXPLAINED",
        }
    ]

    body = _stop_okved_56(api.get(f"{POLICIES}/policy_v10.1", headers=admin).json()["body"])
    updated = api.put(f"{POLICIES}/policy_v10.1", json={"body": body}, headers=admin)
    assert updated.status_code == 200, updated.text
    assert "56" in updated.json()["body"]["stop_factors"]["okved_classes"]
    assert updated.json()["comment"] == "Без общепита"  # не прислали — прежний

    activated = api.post(f"{POLICIES}/policy_v10.1/activate", headers=admin)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert activated.json()["activated_at"] is not None
    assert _statuses(app) == {BUILTIN: "archived", "policy_v10.1": "active"}

    # Активная версия неизменна.
    for method, path, payload in [
        ("PUT", f"{POLICIES}/policy_v10.1", {"body": body}),
        ("DELETE", f"{POLICIES}/policy_v10.1", None),
        ("POST", f"{POLICIES}/policy_v10.1/activate", None),
    ]:
        response = api.request(method, path, json=payload, headers=admin)
        assert response.status_code == 409, path
        assert response.json()["code"] == "invalid_transition"

    second = api.post(POLICIES, json={"based_on": "policy_v10.1"}, headers=admin).json()
    assert second["version"] == "policy_v10.2"
    assert api.delete(f"{POLICIES}/policy_v10.2", headers=admin).status_code == 204
    assert api.get(f"{POLICIES}/policy_v10.2", headers=admin).status_code == 404

    # Вернуть встроенную.
    restored = api.post(f"{POLICIES}/{BUILTIN}/activate", headers=admin)
    assert restored.status_code == 200, restored.text
    assert (restored.json()["version"], restored.json()["status"]) == (BUILTIN, "active")
    assert _statuses(app) == {BUILTIN: "active", "policy_v10.1": "archived"}


def _decision(app: App) -> Any:
    async def read() -> Any:
        async with app.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
            facade = app.client.app.state.facades.get(DecisionFacade, session)  # type: ignore[attr-defined]
            return await facade.get_decision(app.world.application_id)

    return app.run(read)


def test_preview_and_then_the_command_go_by_the_new_version(app: App) -> None:
    api, admin = app.client, _admin(app)
    application_id = app.world.application_id
    app.send(MakeDecision(application_id=application_id), application_id, "process")
    assert _decision(app).policy_version == BUILTIN

    draft = api.post(POLICIES, json={"based_on": BUILTIN}, headers=admin).json()
    version = draft["version"]
    api.put(f"{POLICIES}/{version}", json={"body": _stop_okved_56(draft["body"])}, headers=admin)

    preview = api.post(f"{POLICIES}/{version}/preview?limit=10", headers=_reader(app))

    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert (data["total"], data["changed"], data["outcome_changed"], data["skipped"]) == (
        1,
        1,
        1,
        0,
    )
    [item] = data["items"]
    assert item["application_id"] == str(application_id)
    assert (item["before"]["outcome"], item["before"]["policy_version"]) == ("APPROVE", BUILTIN)
    assert (item["after"]["outcome"], item["after"]["policy_version"]) == ("REJECT", version)
    assert item["after"]["reason_codes"] == ["STOP_FORBIDDEN_OKVED"]
    assert data["transitions"] == [{"from": "APPROVE", "to": "REJECT", "count": 1}]
    assert api.post(f"{POLICIES}/{version}/preview?limit=0", headers=admin).status_code == 422
    assert _decision(app).policy_version == BUILTIN  # примерка ничего не пишет

    # Активировали — следующая команда процесса решается этой версией.
    assert api.post(f"{POLICIES}/{version}/activate", headers=admin).status_code == 200
    app.send(MakeDecision(application_id=application_id), application_id, "process")

    decision = _decision(app)
    assert (decision.policy_version, decision.outcome) == (version, "REJECT")
    assert "STOP_FORBIDDEN_OKVED" in decision.reason_codes
    assert app.envelopes("DecisionMade")[-1]["payload"]["outcome"] == "REJECT"
