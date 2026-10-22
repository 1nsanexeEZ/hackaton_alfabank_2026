"""Сквозные golden-тесты оценки заявки (#41) на реальных фасадах и сидах §9.

Каждый сценарий: заявка подаётся через API от демо-аккаунта → команда `FetchEnrichment` →
ответ `EnrichmentCompleted` → команда `CalculateScore` → ответ `ScoreCalculated`. Числа совпадают с
golden scoring (`tests/scoring/golden`), потому что входы те же: данные моков и каталог продуктов.
Страховка для e2e: если поменяется контракт соседа, это видно здесь, а не на демо.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.clients.facade import ClientsFacade, OrgPermission
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import PermissionDeniedError
from src.enrichment import module as enrichment_module
from src.enrichment.facade import EnrichmentFacade
from src.main import create_app
from src.scoring.facade import ScoringFacade
from tests.assessment.assessment_world import NOW, Assessment, mock_sources
from tests.fakes.document_storage import FakeDocumentStorage
from tests.helpers import create_schema

_ASSESSMENT_TOPICS = {"enrichment.commands", "scoring.commands"}


@dataclass(frozen=True, kw_only=True)
class Scenario:
    name: str
    email: str
    inn: str
    product: str
    amount: str
    term: int
    purpose: str = "working_capital"
    documents: tuple[str, ...] = ()
    statement: str | None = None
    collateral: dict[str, Any] | None = None
    product_fields: dict[str, Any] | None = None
    # ожидания
    sources_failed: tuple[str, ...] = ()
    cash_gap: bool | None = None
    gap_month: str | None = None
    score: int
    grade: str
    flags: frozenset[str] = field(default_factory=frozenset)


SCENARIOS = (
    Scenario(
        name="S-1 romashka UNSECURED 3 млн",
        email="owner@romashka.test",
        inn="7701158817",
        product="UNSECURED",
        amount="3000000",
        term=24,
        score=790,
        grade="A",
    ),
    Scenario(
        name="S-2 ivanov UNSECURED 5 млн с выпиской",
        email="ivanov@ip.test",
        inn="770669871605",
        product="UNSECURED",
        amount="5000000",
        term=24,
        documents=("tax_return",),
        statement="ivanov",
        cash_gap=True,
        gap_month="2026-11",
        score=565,
        grade="C",
        flags=frozenset({"thin_file", "cash_gap"}),
    ),
    Scenario(
        name="S-3 vector CREDIT_LINE 10 млн",
        email="petrov@vector.test",
        inn="7702987976",
        product="CREDIT_LINE",
        amount="10000000",
        term=24,
        documents=("financial_report",),
        score=620,
        grade="C",
        flags=frozenset({"verification_mismatch"}),
    ),
    Scenario(
        name="S-4 zakat UNSECURED 2 млн",
        email="owner@zakat.test",
        inn="7703417070",
        product="UNSECURED",
        amount="2000000",
        term=12,
        score=395,
        grade="E",
    ),
    Scenario(
        name="S-5 progress CREDIT_LINE 8 млн",
        email="owner@progress.test",
        inn="7704568152",
        product="CREDIT_LINE",
        amount="8000000",
        term=24,
        documents=("financial_report",),
        score=700,
        grade="B",
        flags=frozenset({"revenue_mismatch"}),
    ),
    Scenario(
        name="S-6 sboy UNSECURED 1 млн, БКИ недоступно",
        email="owner@sboy.test",
        inn="7705729405",
        product="UNSECURED",
        amount="1000000",
        term=12,
        sources_failed=("bki",),
        score=760,
        grade="A",
        flags=frozenset({"bureau_unavailable"}),
    ),
    Scenario(
        name="S-7 romashka MORTGAGE 30 млн с залогом",
        email="owner@romashka.test",
        inn="7701158817",
        product="MORTGAGE",
        amount="30000000",
        term=120,
        purpose="real_estate",
        documents=("financial_report", "purchase_contract", "collateral_documents"),
        collateral={
            "type": "real_estate",
            "description": "Офис, г. Москва, ул. Тверская, д. 10",
            "declared_value": "50000000",
            "owner": "self",
        },
        product_fields={
            "property_address": "г. Москва, ул. Тверская, д. 10",
            "property_type": "office",
            "price": 50000000,
        },
        score=700,
        grade="B",
    ),
)


@pytest.fixture(scope="module")
def assessment(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Assessment]:
    folder = tmp_path_factory.mktemp("assessment")
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(folder / 'assessment.db').as_posix()}",
        jwt_private_key_path=folder / "keys" / "private.pem",
        jwt_public_key_path=folder / "keys" / "public.pem",
        messaging_mode="manual",
        minio_ensure_bucket=False,
        seed_demo_data=True,
    )
    app = create_app(settings, clock=FrozenClock(NOW))
    storage = FakeDocumentStorage()
    app.state.document_storage = storage
    create_schema(settings.database_url)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(enrichment_module, "_sources", mock_sources())
        with TestClient(app) as client:
            yield Assessment(client, storage)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_enrichment_and_scoring(assessment: Assessment, scenario: Scenario) -> None:
    application_id = assessment.apply(
        email=scenario.email,
        inn=scenario.inn,
        product=scenario.product,
        amount=scenario.amount,
        term=scenario.term,
        purpose=scenario.purpose,
        documents=scenario.documents,
        statement=scenario.statement,
        collateral=scenario.collateral,
        product_fields=scenario.product_fields,
    )

    enriched = assessment.fetch_enrichment(application_id)
    expected_ok = {"egrul", "fns", "bki"} - set(scenario.sources_failed)
    assert set(enriched["sources_ok"]) == expected_ok
    assert enriched["sources_failed"] == list(scenario.sources_failed)
    assert enriched["cash_gap_detected"] is scenario.cash_gap
    if scenario.gap_month is not None:
        snapshot = assessment.facade(EnrichmentFacade, lambda f: f.get_snapshot(application_id))
        assert snapshot is not None and snapshot.cashflow is not None
        assert snapshot.cashflow.gap_month == scenario.gap_month

    scored = assessment.calculate_score(application_id)
    assert (scored["score"], scored["risk_grade"]) == (scenario.score, scenario.grade)
    assert set(scored["flags"]) == scenario.flags

    result = assessment.facade(ScoringFacade, lambda f: f.get_result(application_id))
    assert result is not None and result.score == scenario.score

    stuck = [d for d in assessment.dead_letters() if d["topic"] in _ASSESSMENT_TOPICS]
    assert stuck == []


def test_s8_accountant_cannot_sign(assessment: Assessment) -> None:
    accountant = assessment.account_id("accountant@romashka.test")
    romashka = assessment.organization_id("7701158817")

    with pytest.raises(PermissionDeniedError):
        assessment.facade(
            ClientsFacade, lambda f: f.ensure_can(accountant, romashka, OrgPermission.SIGN)
        )
