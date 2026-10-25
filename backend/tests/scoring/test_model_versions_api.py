"""Ручки версий PD-модели: чтение и примерка — `scoring.read`, ведение — `scoring.update`."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.main import create_app
from src.modules.scoring.application.serialization import dump_input, input_hash
from src.modules.scoring.domain.model import ScoringResult
from src.modules.scoring.infrastructure.config_loader import load_pd_model
from src.modules.scoring.infrastructure.repository import SqlAlchemyScoringRepository
from tests.helpers import bearer, create_schema, token_for
from tests.scoring.scenarios import SCENARIOS

MODELS = "/scoring/models"


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    create_schema(settings.database_url)
    return create_app(settings)


@pytest.fixture
def api(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def _admin(app: FastAPI) -> dict[str, str]:
    return bearer(token_for(app, [Permissions.ADMIN]))


def _reader(app: FastAPI) -> dict[str, str]:
    """Как у андеррайтера: читать и примерять, но не править."""
    return bearer(token_for(app, [Permissions.SCORING_READ, Permissions.DECISIONS_READ]))


def test_reader_sees_the_models_but_does_not_keep_them(api: TestClient, app: FastAPI) -> None:
    reader = _reader(app)

    versions = api.get(MODELS, headers=reader)
    assert versions.status_code == 200, versions.text
    assert [(v["version"], v["status"], v["builtin"]) for v in versions.json()] == [
        ("pd_model_v2", "active", True)
    ]
    builtin = api.get(f"{MODELS}/pd_model_v2", headers=reader).json()
    assert builtin["body"]["version"] == "pd_model_v2"
    assert set(builtin["body"]["scorecards"]) == {"legal_entity", "entrepreneur", "new_client"}

    catalog = api.get(f"{MODELS}/catalog", headers=reader).json()
    assert catalog["segments"] == ["legal_entity", "entrepreneur", "new_client"]
    assert catalog["grades"][0] == "A" and catalog["worst_grade"] == "J"
    features = {f["code"]: f for f in catalog["features"]}
    assert features["debt_load"] == {
        "code": "debt_load",
        "kind": "numeric",
        "categories": [],
        "required": True,
    }
    assert features["bureau_overdue"]["categories"] == ["thin"]
    assert features["cash_gap"]["kind"] == "categorical"

    for method, path, body in [
        ("POST", MODELS, {"based_on": "pd_model_v2"}),
        ("PUT", f"{MODELS}/pd_model_v2", {"body": builtin["body"]}),
        ("DELETE", f"{MODELS}/pd_model_v2", None),
        ("POST", f"{MODELS}/pd_model_v2/activate", None),
    ]:
        response = api.request(method, path, json=body, headers=reader)
        assert response.status_code == 403, path

    outsider = bearer(token_for(app, [Permissions.DECISIONS_READ]))
    assert api.get(MODELS, headers=outsider).status_code == 403
    assert api.get(MODELS).status_code == 401


def test_admin_drafts_checks_activates_and_rolls_back(api: TestClient, app: FastAPI) -> None:
    admin = _admin(app)

    created = api.post(
        MODELS, json={"based_on": "pd_model_v2", "comment": "Строже к долгу"}, headers=admin
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert (draft["version"], draft["status"], draft["based_on"]) == (
        "pd_model_v2.1",
        "draft",
        "pd_model_v2",
    )
    body = draft["body"]

    # Дырявые бины — 422 со списком {path, message}.
    broken = {**body, "scorecards": {**body["scorecards"]}}
    card = broken["scorecards"]["legal_entity"] = {**body["scorecards"]["legal_entity"]}
    features = card["features"] = dict(card["features"])
    features["debt_load"] = {**features["debt_load"], "bins": features["debt_load"]["bins"][1:]}
    rejected = api.put(f"{MODELS}/pd_model_v2.1", json={"body": broken}, headers=admin)
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["code"] == "validation_error"
    assert rejected.json()["details"]["errors"] == [
        {
            "path": "scorecards.legal_entity.features.debt_load.bins",
            "message": "бины не покрывают значения ниже 0.2",
        }
    ]

    body["scorecards"]["legal_entity"]["base"] = 650
    updated = api.put(f"{MODELS}/pd_model_v2.1", json={"body": body}, headers=admin)
    assert updated.status_code == 200, updated.text
    assert updated.json()["body"]["scorecards"]["legal_entity"]["base"] == 650
    assert updated.json()["comment"] == "Строже к долгу"  # не прислали — прежний

    activated = api.post(f"{MODELS}/pd_model_v2.1/activate", headers=admin)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert activated.json()["activated_at"] is not None
    statuses = {v["version"]: v["status"] for v in api.get(MODELS, headers=admin).json()}
    assert statuses == {"pd_model_v2": "archived", "pd_model_v2.1": "active"}

    # Активная версия неизменна.
    for method, path, payload in [
        ("PUT", f"{MODELS}/pd_model_v2.1", {"body": body}),
        ("DELETE", f"{MODELS}/pd_model_v2.1", None),
        ("POST", f"{MODELS}/pd_model_v2.1/activate", None),
    ]:
        response = api.request(method, path, json=payload, headers=admin)
        assert response.status_code == 409, path
        assert response.json()["code"] == "invalid_transition"

    second = api.post(MODELS, json={"based_on": "pd_model_v2.1"}, headers=admin).json()
    assert second["version"] == "pd_model_v2.2"
    assert api.delete(f"{MODELS}/pd_model_v2.2", headers=admin).status_code == 204
    assert api.get(f"{MODELS}/pd_model_v2.2", headers=admin).status_code == 404

    # Вернуть встроенную.
    restored = api.post(f"{MODELS}/pd_model_v2/activate", headers=admin)
    assert restored.status_code == 200, restored.text
    assert (restored.json()["version"], restored.json()["status"]) == ("pd_model_v2", "active")
    statuses = {v["version"]: v["status"] for v in api.get(MODELS, headers=admin).json()}
    assert statuses == {"pd_model_v2": "active", "pd_model_v2.1": "archived"}


async def _scored(database_url: str) -> None:
    """Заявка Ромашки, посчитанная встроенной моделью."""
    model = load_pd_model()
    scoring_input = SCENARIOS["romashka_s1"]
    output = model.calculate(scoring_input)
    stored = dump_input(scoring_input)
    engine = create_async_engine(database_url)
    async with async_sessionmaker(engine)() as session:
        await SqlAlchemyScoringRepository(session).add(
            ScoringResult(
                id=uuid4(),
                application_id=uuid4(),
                requested_by_command=uuid4(),
                model_version=model.version,
                score=output.score,
                grade=output.grade,
                factors=output.factors,
                flags=output.flags,
                data_completeness=output.data_completeness,
                computed_at=datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
                input_hash=input_hash(stored),
                segment=output.segment,
                scorecard=output.scorecard,
                pd_12m=output.pd_12m,
                reason_codes=output.reason_codes,
            ),
            input_snapshot=stored,
        )
        await session.commit()
    await engine.dispose()


def test_preview_shows_grades_before_and_after(
    api: TestClient, app: FastAPI, settings: Settings
) -> None:
    asyncio.run(_scored(settings.database_url))
    admin = _admin(app)
    draft = api.post(MODELS, json={"based_on": "pd_model_v2"}, headers=admin).json()
    body = draft["body"]
    body["scorecards"]["legal_entity"]["base"] -= 300
    api.put(f"{MODELS}/{draft['version']}", json={"body": body}, headers=admin)

    preview = api.post(f"{MODELS}/{draft['version']}/preview?limit=10", headers=_reader(app))

    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert (data["total"], data["worse"], data["same"], data["skipped"]) == (1, 1, 0, 0)
    [item] = data["items"]
    assert item["before"]["model_version"] == "pd_model_v2"
    assert item["after"]["model_version"] == "pd_model_v2.1"
    assert item["after"]["score"] == item["before"]["score"] - 300
    assert data["transitions"] == [
        {"from": item["before"]["grade"], "to": item["after"]["grade"], "count": 1}
    ]
    assert api.post(f"{MODELS}/pd_model_v2.1/preview?limit=0", headers=admin).status_code == 422
