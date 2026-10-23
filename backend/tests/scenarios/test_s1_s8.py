"""Scenarios S-1…S-10 end to end: the real application with every module and
the demo seeds, the process drives the pipeline by itself. Only the outside
world is played: answers of the external mocks (registry, tax, credit bureau)
come through `httpx.MockTransport`, files lie in memory.

What the client and the underwriter do goes through the public HTTP API, the
messages between modules go through the same subscriptions as in Kafka.
"""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.main import create_app
from src.modules.enrichment import module as enrichment_module
from tests.assessment.assessment_world import NOW, Assessment, mock_sources
from tests.fakes.document_storage import FakeDocumentStorage
from tests.helpers import bearer, create_schema

DEMO_PASSWORD = "Demo-2026!"


class Stand(Assessment):
    """The assessment world plus what a person does on screens."""

    def settle(self) -> None:
        self.run(self.client.app.state.messaging.drain)  # type: ignore[attr-defined]

    def login(self, email: str) -> dict[str, str]:
        response = self.client.post("/auth/login", json={"login": email, "password": DEMO_PASSWORD})
        assert response.status_code == 200, response.text
        return bearer(response.json()["access_token"])

    def card(self, application_id: UUID, email: str) -> dict[str, Any]:
        response = self.client.get(f"/applications/{application_id}", headers=self.login(email))
        assert response.status_code == 200, response.text
        return response.json()

    def process(self, application_id: UUID) -> dict[str, Any]:
        response = self.client.get(
            f"/processes/{application_id}", headers=self.login("underwriter@bank.test")
        )
        assert response.status_code == 200, response.text
        return response.json()

    def task_for(self, application_id: UUID) -> dict[str, Any]:
        tasks = self.client.get("/tasks", headers=self.login("underwriter@bank.test")).json()
        [task] = [t for t in tasks if t["application_id"] == str(application_id)]
        return task

    def underwriter_decides(self, application_id: UUID, result: dict[str, Any]) -> None:
        headers = self.login("underwriter@bank.test")
        task = self.task_for(application_id)
        claimed = self.client.post(f"/tasks/{task['id']}/claim", headers=headers)
        assert claimed.status_code == 200, claimed.text
        done = self.client.post(f"/tasks/{task['id']}/complete", json=result, headers=headers)
        assert done.status_code == 200, done.text
        self.settle()

    def accept_and_sign(self, application_id: UUID, email: str) -> dict[str, Any]:
        headers = self.login(email)
        accepted = self.client.post(f"/applications/{application_id}/offer/accept", headers=headers)
        assert accepted.status_code == 200, accepted.text
        self.settle()
        signed = self.client.post(
            f"/applications/{application_id}/sign",
            json={
                "password": DEMO_PASSWORD,
                "offer_hash": self.offer_hash(application_id, headers),
            },
            headers=headers,
        )
        assert signed.status_code == 200, signed.text
        self.settle()
        return self.card(application_id, email)

    def offer_hash(self, application_id: UUID, headers: dict[str, str]) -> str:
        """The client reads the contract before signing it."""
        contract = self.client.get(f"/applications/{application_id}/contract", headers=headers)
        assert contract.status_code == 200, contract.text
        assert contract.json()["status"] == "unsigned"
        return contract.json()["offer_hash"]

    def stuck(self) -> list[Any]:
        return list(self.dead_letters())


@pytest.fixture
def stand(tmp_path: Any) -> Iterator[Stand]:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'stand.db').as_posix()}",
        jwt_private_key_path=tmp_path / "keys" / "private.pem",
        jwt_public_key_path=tmp_path / "keys" / "public.pem",
        messaging_mode="manual",
        minio_ensure_bucket=False,
        run_background_jobs=False,
        seed_demo_data=True,
    )
    app = create_app(settings, clock=FrozenClock(NOW))
    storage = FakeDocumentStorage()
    app.state.document_storage = storage
    create_schema(settings.database_url)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(enrichment_module, "_sources", mock_sources())
        with TestClient(app) as client:
            yield Stand(client, storage)


def submit(stand: Stand, **application: Any) -> UUID:
    application_id = stand.apply(**application)
    stand.settle()
    return application_id


ROMASHKA = {"email": "owner@romashka.test", "inn": "7701158817"}


def test_s1_romashka_is_approved_signed_and_paid(stand: Stand) -> None:
    application_id = submit(stand, **ROMASHKA, product="UNSECURED", amount="3000000", term=24)

    card = stand.card(application_id, ROMASHKA["email"])
    assert card["status"] == "offer_ready"
    assert card["offer"]["kind"] == "as_requested"
    assert Decimal(card["offer"]["amount"]) == Decimal("3000000")
    assert card["decision_summary"]["outcome"] == "APPROVE"
    assert card["client_stage"] == "Решение готово"

    card = stand.accept_and_sign(application_id, ROMASHKA["email"])
    assert card["status"] == "disbursed"
    assert card["disbursement"]["simulated"] is True
    process = stand.process(application_id)
    assert process["status"] == "completed"
    assert "underwriter_review" not in process["visited_node_ids"]
    assert stand.stuck() == []


def test_s2_ivanov_is_checked_by_the_underwriter(stand: Stand) -> None:
    """policy_v5: PD-модель и ML-модель обе в жёлтой зоне (грейд E) — проверка андеррайтером,
    он делает встречное предложение."""
    application_id = submit(
        stand,
        email="ivanov@ip.test",
        inn="770669871605",
        product="UNSECURED",
        amount="5000000",
        term=24,
        documents=("tax_return",),
        statement="ivanov",
    )
    card = stand.card(application_id, "ivanov@ip.test")
    assert card["status"] == "in_review"
    assert card["client_stage"] == "Заявка у специалиста"

    stand.underwriter_decides(
        application_id,
        {
            "decision": "counter_offer",
            "amount": "3000000",
            "term_months": 24,
            "rate": "25",
            "comment": "Обе модели в жёлтой зоне, кассовый разрыв в ноябре: снижаем сумму",
        },
    )
    card = stand.card(application_id, "ivanov@ip.test")
    assert card["status"] == "offer_ready"
    assert card["offer"]["kind"] == "counter"
    assert Decimal(card["offer"]["amount"]) == Decimal("3000000")
    assert stand.stuck() == []


def test_s3_vector_goes_to_the_underwriter(stand: Stand) -> None:
    application_id = submit(
        stand,
        email="petrov@vector.test",
        inn="7702987976",
        product="CREDIT_LINE",
        amount="10000000",
        term=24,
        documents=("financial_report",),
    )
    card = stand.card(application_id, "petrov@vector.test")
    assert card["status"] == "in_review"
    assert card["client_stage"] == "Заявка у специалиста"

    stand.underwriter_decides(
        application_id,
        {
            "decision": "counter_offer",
            "amount": "6000000",
            "term_months": 24,
            "rate": "24",
            "comment": "Руководитель в ЕГРЮЛ другой: снижаем лимит до подтверждения полномочий",
        },
    )
    card = stand.card(application_id, "petrov@vector.test")
    assert card["status"] == "offer_ready"
    assert Decimal(card["offer"]["amount"]) == Decimal("6000000")
    assert stand.stuck() == []


def test_s4_zakat_is_rejected(stand: Stand) -> None:
    application_id = submit(
        stand,
        email="owner@zakat.test",
        inn="7703417070",
        product="UNSECURED",
        amount="2000000",
        term=12,
    )
    card = stand.card(application_id, "owner@zakat.test")
    assert card["status"] == "rejected"
    assert card["decision_summary"]["outcome"] == "REJECT"
    assert card["decision_summary"]["client_explanation"]
    process = stand.process(application_id)
    assert process["status"] == "completed"
    # Ликвидация, просрочки, недоимка — отказ на шаге «Стоп-факторы», модель не вызывается.
    assert process["visited_node_ids"][-2:] == ["check_stop_factors", "reject"]
    assert "calculate_score" not in process["visited_node_ids"]
    assert stand.stuck() == []


def test_s5_progress_is_asked_for_a_statement_then_reviewed(stand: Stand) -> None:
    email = "owner@progress.test"
    application_id = submit(
        stand,
        email=email,
        inn="7704568152",
        product="CREDIT_LINE",
        amount="8000000",
        term=24,
        documents=("financial_report",),
    )
    card = stand.card(application_id, email)
    assert card["status"] == "info_requested"
    [request] = [r for r in card["info_requests"] if r["status"] == "open"]
    assert "bank_statement" in request["requested_documents"]

    stand.answer_with_statement(
        application_id, UUID(request["id"]), email=email, statement="progress"
    )
    stand.settle()

    card = stand.card(application_id, email)
    assert card["status"] == "in_review"
    assert card["client_stage"] == "Заявка у специалиста"
    assert stand.task_for(application_id)["status"] == "open"
    assert stand.stuck() == []


def test_s6_sboy_without_credit_bureau_goes_to_the_underwriter(stand: Stand) -> None:
    application_id = submit(
        stand,
        email="owner@sboy.test",
        inn="7705729405",
        product="UNSECURED",
        amount="1000000",
        term=12,
    )
    assert stand.card(application_id, "owner@sboy.test")["status"] == "in_review"
    assert stand.task_for(application_id)["status"] == "open"
    assert stand.stuck() == []


def test_s7_mortgage_is_always_decided_by_a_person(stand: Stand) -> None:
    application_id = submit(
        stand,
        **ROMASHKA,
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
    )
    assert stand.card(application_id, ROMASHKA["email"])["status"] == "in_review"
    process = stand.process(application_id)
    assert process["workflow_code"] == "mortgage_v2"
    assert "assess_collateral" in process["visited_node_ids"]

    approval = {
        "decision": "approve",
        "amount": "30000000",
        "term_months": 120,
        "rate": "18",
        "comment": "Залог покрывает сумму с дисконтом, выручка стабильная",
    }
    # 18% is below the product's rates (23–28%): the policy turns the decision
    # down and the application comes back to the underwriter as a new task.
    first_task = stand.task_for(application_id)
    stand.underwriter_decides(application_id, approval)
    assert stand.card(application_id, ROMASHKA["email"])["status"] == "in_review"
    second_task = stand.task_for(application_id)
    assert second_task["id"] != first_task["id"]

    stand.underwriter_decides(application_id, {**approval, "rate": "23.5"})
    card = stand.card(application_id, ROMASHKA["email"])
    assert card["status"] == "offer_ready"
    assert Decimal(card["offer"]["rate"]) == Decimal("23.5")
    assert stand.stuck() == []


def test_s8_accountant_submits_but_only_the_director_signs(stand: Stand) -> None:
    accountant = "accountant@romashka.test"
    application_id = submit(
        stand, email=accountant, inn="7701158817", product="UNSECURED", amount="3000000", term=24
    )

    headers = stand.login(accountant)
    card = stand.card(application_id, accountant)
    assert card["status"] == "offer_ready"
    assert "sign" not in card["my_permissions"]
    accepted = stand.client.post(f"/applications/{application_id}/offer/accept", headers=headers)
    assert accepted.status_code == 200
    seen = stand.offer_hash(application_id, headers)  # the accountant may read the contract
    denied = stand.client.post(
        f"/applications/{application_id}/sign",
        json={"password": DEMO_PASSWORD, "offer_hash": seen},
        headers=headers,
    )
    assert denied.status_code == 403

    director = stand.login(ROMASHKA["email"])
    signed = stand.client.post(
        f"/applications/{application_id}/sign",
        json={"password": DEMO_PASSWORD, "offer_hash": stand.offer_hash(application_id, director)},
        headers=director,
    )
    assert signed.status_code == 200, signed.text
    stand.settle()
    assert stand.card(application_id, ROMASHKA["email"])["status"] == "disbursed"


START = {"email": "owner@start.test", "inn": "7706123455"}


def test_s9_startup_founder_prescreen_project_assessment_and_offer(stand: Stand) -> None:
    """A company without turnover: the founder's prescreen instead of pre-approval, a STARTUP
    application, the underwriter's project assessment, an offer, signing and the money."""
    founder = stand.login(START["email"])
    organization_id = stand.organization_id(START["inn"])

    dashboard = stand.client.get("/bff/dashboard", headers=founder).json()
    assert dashboard["organization"]["segment"] == "startup"
    assert dashboard["pre_approved"] == []
    assert dashboard["startup"] == {
        "prescreen": None,
        "business_plan_revision": None,
        "project": None,
    }

    prescreen_url = f"/organizations/{organization_id}/founder-prescreen"
    no_consent = stand.client.post(prescreen_url, headers=founder)
    assert no_consent.status_code == 422, no_consent.text
    assert no_consent.json()["details"]["code"] == "consent_required"
    consents = stand.client.post(
        "/me/consents", json={"types": ["personal_data", "credit_bureau_personal"]}, headers=founder
    )
    assert consents.status_code == 201, consents.text
    passed = stand.client.post(prescreen_url, headers=founder)
    assert passed.status_code == 201, passed.text
    assert passed.json()["status"] == "passed"
    assert stand.client.get(prescreen_url, headers=founder).json()["status"] == "passed"

    matched = stand.client.get(
        "/bff/products/recommend",
        params={
            "organization_id": str(organization_id),
            "purpose": "working_capital",
            "amount": "3000000",
            "term_months": 36,
        },
        headers=founder,
    ).json()["items"]
    assert [item["product_code"] for item in matched] == ["STARTUP"]

    application_id = submit(
        stand,
        **START,
        product="STARTUP",
        amount="3000000",
        term=36,
        documents=("business_plan", "financial_model"),
    )
    card = stand.card(application_id, START["email"])
    assert card["status"] == "in_review"
    assert card["client_stage"] == "Проектная оценка"
    process = stand.process(application_id)
    assert process["workflow_code"] == "startup_v2"
    task = stand.task_for(application_id)
    assert task["type"] == "project_assessment"
    assert "business_plan" in task["form_schema"]["required"]

    stand.underwriter_decides(
        application_id,
        {
            "decision": "approve",
            "amount": "3000000",
            "term_months": 36,
            "rate": "17",
            "business_plan": "acceptable",
            "collateral": "поручительство учредителя",
            "support_program": True,
            "comment": "Бизнес-план реалистичный, учредитель без просрочек, программа МСП",
        },
    )
    card = stand.card(application_id, START["email"])
    assert card["status"] == "offer_ready"
    assert Decimal(card["offer"]["rate"]) == Decimal("17")

    card = stand.accept_and_sign(application_id, START["email"])
    assert card["status"] == "disbursed"
    assert stand.stuck() == []


def test_s9_startup_without_a_prescreen_is_turned_down(stand: Stand) -> None:
    application_id = submit(
        stand,
        **START,
        product="STARTUP",
        amount="3000000",
        term=36,
        documents=("business_plan", "financial_model"),
    )
    card = stand.card(application_id, START["email"])
    assert card["status"] == "rejected"
    assert card["decision_summary"]["outcome"] == "REJECT"
    assert "учредителя" in card["decision_summary"]["client_explanation"]
    assert stand.stuck() == []


def startup_plan() -> dict[str, Any]:
    """Кофейня: выручка 1 млн и расходы 800 тыс. в месяц, свои 1 млн, гарантия Корпорации МСП
    на половину кредита, нужно 3 млн на 3 года."""
    return {
        "summary": "Кофейня у метро: зерно от обжарщика, завтраки, доставка по району",
        "financial_model": {
            "months": [{"revenue": "1000000", "expenses": "800000"}] * 24,
            "own_funds": "1000000",
            "collateral_description": "Поручительство учредителя",
            "guarantee": "msp_corporation",
            "guarantee_share": "0.5",
            "loan_amount": "3000000",
            "loan_term_months": 36,
        },
    }


def test_s10_startup_business_plan_pre_approval_application_and_offer(stand: Stand) -> None:
    """The startup's way of the target scheme: the founder's prescreen → the business plan and
    the financial model in the cabinet → the project assessment → «pre-approved up to N» → a
    STARTUP application → the underwriter confirms the filled in project assessment → an offer,
    signing and the money."""
    founder = stand.login(START["email"])
    organization_id = stand.organization_id(START["inn"])
    consents = stand.client.post(
        "/me/consents", json={"types": ["personal_data", "credit_bureau_personal"]}, headers=founder
    )
    assert consents.status_code == 201, consents.text
    prescreen = stand.client.post(
        f"/organizations/{organization_id}/founder-prescreen", headers=founder
    )
    assert prescreen.json()["status"] == "passed"

    assessment_url = f"/organizations/{organization_id}/project-assessment"
    no_plan = stand.client.post(assessment_url, headers=founder)
    assert no_plan.status_code == 422, no_plan.text
    assert no_plan.json()["details"]["code"] == "business_plan_required"
    plan = stand.client.put(
        f"/organizations/{organization_id}/business-plan", json=startup_plan(), headers=founder
    )
    assert plan.status_code == 201, plan.text

    assessed = stand.client.post(assessment_url, headers=founder)
    assert assessed.status_code == 201, assessed.text
    assessment = assessed.json()
    assert assessment["status"] == "passed" and assessment["product_code"] == "STARTUP"
    # Поток 4,8 млн за 24 месяца выдерживает 3,82 млн при DSCR 1,3 по верхней ставке
    # коридора (26%) — вниз до шага суммы.
    assert Decimal(assessment["max_amount"]) == Decimal("3810000")
    assert all(reason["passed"] for reason in assessment["reasons"])
    stand.settle()

    dashboard = stand.client.get("/bff/dashboard", headers=founder).json()
    [offer] = dashboard["pre_approved"]
    assert offer["product_code"] == "STARTUP"
    assert Decimal(offer["max_amount"]) == Decimal("3810000")
    assert dashboard["startup"]["project"]["status"] == "passed"
    assert dashboard["startup"]["business_plan_revision"] == 1
    assert any("предодобрен" in item["title"] for item in dashboard["feed"]["items"])
    [listed] = stand.client.get(
        f"/organizations/{organization_id}/pre-approved-offers", headers=founder
    ).json()
    assert listed["basis"] == "project"

    application_id = submit(
        stand,
        **START,
        product="STARTUP",
        amount="3000000",
        term=36,
        documents=("business_plan", "financial_model"),
    )
    card = stand.card(application_id, START["email"])
    assert card["status"] == "in_review"
    assert card["client_stage"] == "Проектная оценка"

    underwriter_card = stand.client.get(
        f"/bff/backoffice/applications/{application_id}",
        headers=stand.login("underwriter@bank.test"),
    ).json()
    startup = underwriter_card["startup"]
    assert startup["valid_at_submission"] and not startup["plan_changed"]
    assert Decimal(startup["assessment"]["figures"]["dscr"]) == Decimal("1.65")
    form = startup["form"]
    assert form["decision"] == "approve" and Decimal(form["amount"]) == Decimal("3000000")
    assert form["business_plan"] == "acceptable" and form["support_program"] is True
    assert underwriter_card["task"]["type"] == "project_assessment"

    stand.underwriter_decides(
        application_id,
        {
            **form,
            "amount": str(form["amount"]),
            "rate": "17",
            "comment": "Проект подтверждаю: финмодель реалистичная, гарантия Корпорации МСП",
        },
    )
    card = stand.card(application_id, START["email"])
    assert card["status"] == "offer_ready"
    assert Decimal(card["offer"]["amount"]) == Decimal("3000000")
    assert Decimal(card["offer"]["rate"]) == Decimal("17")

    card = stand.accept_and_sign(application_id, START["email"])
    assert card["status"] == "disbursed"
    assert stand.stuck() == []
