"""Сквозные golden-тесты оценки заявки (#41) на реальных фасадах и сидах §9.

Каждый сценарий: заявка подаётся через API от демо-аккаунта → `FetchEnrichment` →
`EnrichmentCompleted` → `CalculateScore` → `ScoreCalculated` → `MakeDecision` → `DecisionMade`.
Числа скоринга совпадают с golden scoring (`tests/scoring/golden`), исходы решения — с golden
политики (`tests/decision/unit`): входы те же — данные моков и каталог продуктов.
Страховка для e2e: если поменяется контракт соседа, это видно здесь, а не на демо.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import PermissionDeniedError
from src.main import create_app
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.decision.facade import DecisionDTO
from src.modules.enrichment import module as enrichment_module
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.scoring.facade import ScoringFacade
from tests.assessment.assessment_world import NOW, Assessment, mock_sources
from tests.fakes.document_storage import FakeDocumentStorage
from tests.helpers import create_schema

_ASSESSMENT_TOPICS = {"enrichment.commands", "scoring.commands", "decision.commands"}


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
    # обогащение и скоринг
    sources_failed: tuple[str, ...] = ()
    cash_gap: bool | None = None
    gap_month: str | None = None
    score: int
    grade: str
    ml_grade: str  # ML-модель рядом с PD-моделью, та же шкала A–J
    flags: frozenset[str] = field(default_factory=frozenset)
    # решение
    outcome: str
    review: str | None = None  # MANUAL_REVIEW: check или dispute
    reasons: frozenset[str] = field(default_factory=frozenset)  # все должны быть
    any_reason: frozenset[str] = field(default_factory=frozenset)  # хотя бы одна
    offer: str | None = None  # сумма оффера ровно
    offer_between: tuple[str, str] | None = None  # [от, до) для встречного предложения
    alternative: str | None = None
    explains: str | None = None  # что клиент должен прочитать в объяснении


SCENARIOS = (
    Scenario(
        name="S-1 romashka UNSECURED 3 млн",
        email="owner@romashka.test",
        inn="7701158817",
        product="UNSECURED",
        amount="3000000",
        term=24,
        score=800,
        grade="A",
        ml_grade="C",
        outcome="APPROVE",
        offer="3000000",
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
        grade="E",
        ml_grade="E",
        flags=frozenset({"thin_file", "cash_gap"}),
        # policy_v5: обе модели в жёлтой зоне — проверка андеррайтером (в policy_v4 —
        # встречное предложение с овердрафтом).
        outcome="MANUAL_REVIEW",
        review="check",
        reasons=frozenset({"ROUTE_MODELS_CHECK"}),
        explains="посмотрит заявку",
    ),
    Scenario(
        name="S-3 vector CREDIT_LINE 10 млн",
        email="petrov@vector.test",
        inn="7702987976",
        product="CREDIT_LINE",
        amount="10000000",
        term=24,
        documents=("financial_report",),
        score=630,
        grade="F",
        ml_grade="F",
        flags=frozenset({"verification_mismatch"}),
        outcome="MANUAL_REVIEW",
        review="dispute",
        reasons=frozenset({"ROUTE_VERIFICATION_MISMATCH", "ROUTE_MODELS_CHECK"}),
    ),
    Scenario(
        name="S-4 zakat UNSECURED 2 млн",
        email="owner@zakat.test",
        inn="7703417070",
        product="UNSECURED",
        amount="2000000",
        term=12,
        score=400,
        grade="J",
        ml_grade="J",
        outcome="REJECT",
        reasons=frozenset({"STOP_LIQUIDATION", "STOP_OVERDUE_90"}),
    ),
    Scenario(
        name="S-6 sboy UNSECURED 1 млн, БКИ недоступно",
        email="owner@sboy.test",
        inn="7705729405",
        product="UNSECURED",
        amount="1000000",
        term=12,
        sources_failed=("bki",),
        score=775,
        grade="B",
        ml_grade="C",
        flags=frozenset({"bureau_unavailable"}),
        outcome="MANUAL_REVIEW",
        review="dispute",
        reasons=frozenset({"ROUTE_SOURCES_FAILED"}),
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
        score=715,
        grade="C",
        ml_grade="D",
        outcome="MANUAL_REVIEW",
        review="check",
        reasons=frozenset({"ROUTE_AMOUNT_OVER_AUTO_LIMIT"}),
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
def test_assessment_scenario(assessment: Assessment, scenario: Scenario) -> None:
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
    # ГИР БО и Контур отвечают по всем демо-компаниям; БКИ руководителя без его согласия не
    # запрашивается — ни в ok, ни в failed. Проверка по 115-ФЗ — на каждой заявке.
    external = {"egrul", "fns", "bki", "gir_bo", "kontur", "aml"}
    expected_ok = external - set(scenario.sources_failed)
    assert set(enriched["sources_ok"]) == expected_ok
    assert "bki_head" not in enriched["sources_ok"] + enriched["sources_failed"]
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
    assert result.ml is not None and result.ml.grade == scenario.ml_grade, result.ml

    made = assessment.make_decision(application_id)
    assert made["outcome"] == scenario.outcome
    assert made["decided_by"] == "auto"
    assert made.get("alternative_product_code") == scenario.alternative
    _check_offer(made, scenario)
    decision = assessment.decision(application_id)
    assert decision is not None and decision.outcome == scenario.outcome
    assert decision.review == scenario.review
    assert scenario.reasons <= set(decision.reason_codes), decision.reason_codes
    if scenario.any_reason:
        assert scenario.any_reason & set(decision.reason_codes), decision.reason_codes
    _check_client_view(assessment, application_id, decision, scenario.explains)

    assert _stuck(assessment) == []


def test_s5_progress_request_info_then_manual_review(assessment: Assessment) -> None:
    """S-5: выручка не подтверждена → дозапрос выписки → после выписки — к андеррайтеру."""
    email = "owner@progress.test"
    application_id = assessment.apply(
        email=email,
        inn="7704568152",
        product="CREDIT_LINE",
        amount="8000000",
        term=24,
        documents=("financial_report",),
    )
    enriched = assessment.fetch_enrichment(application_id)
    assert enriched["cash_gap_detected"] is None  # выписки ещё нет
    scored = assessment.calculate_score(application_id)
    assert (scored["score"], scored["risk_grade"]) == (705, "C")
    assert "revenue_mismatch" in scored["flags"]

    # S-5a: просим выписку, а не отказываем и не отправляем к андеррайтеру
    asked = assessment.make_decision(application_id)
    assert asked["outcome"] == "REQUEST_INFO"
    assert "bank_statement" in asked["requested_info"]["documents"]
    first = assessment.decision(application_id)
    assert first is not None and "INFO_REVENUE_NOT_CONFIRMED" in first.reason_codes
    _check_client_view(assessment, application_id, first, None)

    info_request_id = assessment.request_statement(
        application_id, asked["requested_info"]["comment"]
    )
    assessment.answer_with_statement(
        application_id, info_request_id, email=email, statement="progress"
    )

    # Выписка подтверждает ФНС (12 млн), а не заявленные 36 млн
    assessment.fetch_enrichment(application_id)
    snapshot = assessment.facade(EnrichmentFacade, lambda f: f.get_snapshot(application_id))
    assert snapshot is not None and snapshot.cashflow is not None
    assert snapshot.cashflow.revenue_confirmed is False
    rescored = assessment.calculate_score(application_id)
    assert "revenue_mismatch" in rescored["flags"]

    # S-5b: дозапрос уже был — решает андеррайтер
    routed = assessment.make_decision(application_id)
    assert routed["outcome"] == "MANUAL_REVIEW"
    second = assessment.decision(application_id)
    assert second is not None and "ROUTE_REVENUE_MISMATCH" in second.reason_codes

    assert _stuck(assessment) == []


def test_s8_accountant_cannot_sign(assessment: Assessment) -> None:
    accountant = assessment.account_id("accountant@romashka.test")
    romashka = assessment.organization_id("7701158817")

    with pytest.raises(PermissionDeniedError):
        assessment.facade(
            ClientsFacade, lambda f: f.ensure_can(accountant, romashka, OrgPermission.SIGN)
        )


def _check_offer(made: dict[str, Any], scenario: Scenario) -> None:
    offer = made.get("offer")
    if scenario.offer is None and scenario.offer_between is None:
        assert offer is None
        return
    assert offer is not None
    amount = Decimal(offer["amount"])
    if scenario.offer is not None:
        assert amount == Decimal(scenario.offer)
    if scenario.offer_between is not None:
        low, high = (Decimal(value) for value in scenario.offer_between)
        assert low <= amount < high, amount


def _check_client_view(
    assessment: Assessment, application_id: UUID, decision: DecisionDTO, explains: str | None
) -> None:
    """Клиенту — исход и понятное объяснение, но не внутренние коды и не трасса правил."""
    view = assessment.client_view(application_id)
    assert view is not None and view.outcome == decision.outcome
    assert view.client_explanation
    assert not any(code in view.client_explanation for code in decision.reason_codes)
    if explains is not None:
        assert explains in view.client_explanation.lower()


def _stuck(assessment: Assessment) -> list[Any]:
    return [d for d in assessment.dead_letters() if d["topic"] in _ASSESSMENT_TOPICS]
