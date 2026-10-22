"""Scenarios S-1…S-8 end to end: the real application with every module and
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
            json={"password": DEMO_PASSWORD},
            headers=headers,
        )
        assert signed.status_code == 200, signed.text
        self.settle()
        return self.card(application_id, email)

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


def test_s2_ivanov_gets_a_counter_offer_and_an_alternative(stand: Stand) -> None:
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
    assert card["status"] == "offer_ready"
    assert card["offer"]["kind"] == "counter"
    assert Decimal(card["offer"]["amount"]) < Decimal("5000000")
    assert card["decision_summary"]["outcome"] == "COUNTER_OFFER"
    assert card["decision_summary"]["alternative_product_code"] == "OVERDRAFT"
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
    assert stand.process(application_id)["status"] == "completed"
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
    assert process["workflow_code"] == "mortgage_v1"
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
    denied = stand.client.post(
        f"/applications/{application_id}/sign", json={"password": DEMO_PASSWORD}, headers=headers
    )
    assert denied.status_code == 403

    director = stand.login(ROMASHKA["email"])
    signed = stand.client.post(
        f"/applications/{application_id}/sign", json={"password": DEMO_PASSWORD}, headers=director
    )
    assert signed.status_code == 200, signed.text
    stand.settle()
    assert stand.card(application_id, ROMASHKA["email"])["status"] == "disbursed"
