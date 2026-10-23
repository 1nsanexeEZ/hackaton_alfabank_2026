from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.data import DEMO
from app.dossier import gir_bo_response
from app.main import app
from tests.conftest import DEMO_INNS

_UNKNOWN_VALID = "7707083893"
_CONSENT = {"consent_at": "2026-10-21T10:00:00+00:00", "request_id": "req-1"}


def _person(client: TestClient, fio: str, company_inn: str | None, **extra) -> dict:
    last, first, *middle = fio.split()
    body = {"last_name": last, "first_name": first, "middle_name": middle[0] if middle else None}
    if company_inn is not None:
        body["company_inn"] = company_inn
    resp = client.post("/bki/person-report", json={**body, **_CONSENT, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- ФНС: блокировки счетов -------------------------------------------------------------------


def test_fns_zakat_has_an_account_block(client: TestClient) -> None:
    blocks = client.get("/fns/7703417070").json()["account_blocks"]
    assert blocks == [
        {
            "decision_number": "4512",
            "date": "2026-09-30",
            "authority_code": "7703",
            "reason": "Неуплата налогов",
        }
    ]


def test_fns_romashka_has_no_blocks(client: TestClient) -> None:
    assert client.get("/fns/7701158817").json()["account_blocks"] == []


# --- ГИР БО ---------------------------------------------------------------------------------


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_gir_bo_balance_adds_up(client: TestClient, inn: str) -> None:
    body = client.get(f"/gir-bo/{inn}").json()
    assert body["inn"] == inn and body["unit"] == "тыс. руб."
    for period in body["periods"]:
        balance, income = period["balance"], period["income"]
        assert balance["1600_total_assets"] == balance["1700_total_liabilities"]
        assert (
            balance["1300_equity"]
            + balance["1400_long_term_liabilities"]
            + balance["1500_short_term_liabilities"]
            == balance["1700_total_liabilities"]
        )
        assert income["2200_sales_profit"] == income["2110_revenue"] - income["2120_cost_of_sales"]


def test_gir_bo_romashka_last_two_years(client: TestClient) -> None:
    body = client.get("/gir-bo/7701158817").json()
    last_year = date.today().year - 1
    assert body["available"] is True and body["reason"] is None
    assert [p["year"] for p in body["periods"]] == [last_year - 1, last_year]
    assert body["periods"][-1]["income"]["2110_revenue"] == 48_000


def test_gir_bo_entrepreneur_has_no_reports(client: TestClient) -> None:
    body = client.get("/gir-bo/770669871605").json()
    assert body["available"] is False and body["periods"] == []
    assert "ИП" in body["reason"]


def test_gir_bo_zakat_equity_went_negative(client: TestClient) -> None:
    periods = client.get("/gir-bo/7703417070").json()["periods"]
    assert periods[0]["balance"]["1300_equity"] > 0
    assert periods[-1]["balance"]["1300_equity"] == -2_400


def test_gir_bo_progress_revenue_matches_fns(client: TestClient) -> None:
    gir_bo = client.get("/gir-bo/7704568152").json()["periods"][-1]["income"]["2110_revenue"]
    fns = client.get("/fns/7704568152").json()["revenue_kop"]
    assert gir_bo * 1000 * 100 == fns


def test_gir_bo_young_company_has_no_annual_report() -> None:
    young = replace(DEMO["7701158817"], reg_days_ago=100)
    body = gir_bo_response(young)
    assert body["available"] is False and "менее года" in body["reason"]


def test_gir_bo_generated_is_deterministic(client: TestClient) -> None:
    first = client.get(f"/gir-bo/{_UNKNOWN_VALID}").json()
    assert first == client.get(f"/gir-bo/{_UNKNOWN_VALID}").json()
    assert first["available"] is True and len(first["periods"]) == 2


@pytest.mark.parametrize("path", ["/gir-bo/1234567890", "/kontur/1234567890"])
def test_invalid_inn_404(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


# --- Контур ---------------------------------------------------------------------------------


def test_kontur_romashka_is_clean(client: TestClient) -> None:
    body = client.get("/kontur/7701158817").json()
    assert body["reliability"] == "green"
    assert body["bankruptcy_messages"] == []
    assert body["enforcement_proceedings"] == {"active": 0, "sum_rub": 0}


def test_kontur_zakat_has_enforcement_and_lawsuits(client: TestClient) -> None:
    body = client.get("/kontur/7703417070").json()
    assert body["reliability"] == "red"
    assert body["enforcement_proceedings"] == {"active": 4, "sum_rub": 2_600_000}
    assert body["arbitration"]["as_defendant"] == 6
    assert body["arbitration"]["defendant_sum_rub"] == 5_200_000


def test_kontur_generated_is_deterministic(client: TestClient) -> None:
    first = client.get(f"/kontur/{_UNKNOWN_VALID}").json()
    assert first == client.get(f"/kontur/{_UNKNOWN_VALID}").json()
    assert first["reliability"] in {"green", "yellow", "red"}


# --- БКИ физлица ----------------------------------------------------------------------------


def test_person_report_of_a_demo_head(client: TestClient) -> None:
    body = _person(client, "Смирнова Анна Сергеевна", "7701158817")
    assert body["subject"]["last_name"] == "Смирнова"
    assert [o["type"] for o in body["obligations"]] == ["mortgage", "card"]
    assert all(o["overdue_days"] == 0 for o in body["obligations"])


def test_person_report_zakatov_is_overdue(client: TestClient) -> None:
    body = _person(client, "Закатов Олег Олегович", "7703417070")
    assert max(o["overdue_days"] for o in body["obligations"]) == 45


def test_person_report_name_is_compared_loosely(client: TestClient) -> None:
    body = _person(client, "ЗАКАТОВ  олег олегович", "7703417070")
    assert max(o["overdue_days"] for o in body["obligations"]) == 45


def test_ivanov_has_no_personal_history(client: TestClient) -> None:
    body = _person(client, "Иванов Иван Иванович", "770669871605")
    assert body["obligations"] == [] and body["inquiries_30d"] == 0


def test_person_report_somebody_else_is_generated(client: TestClient) -> None:
    first = _person(client, "Петров Пётр Петрович", "7702987976")
    assert first == _person(client, "Петров Пётр Петрович", "7702987976")


def test_person_report_without_a_company(client: TestClient) -> None:
    body = _person(client, "Петров Пётр Петрович", None)
    assert "obligations" in body and "inquiries_30d" in body


def test_person_report_needs_consent(client: TestClient) -> None:
    resp = client.post(
        "/bki/person-report",
        json={"last_name": "Смирнова", "first_name": "Анна", "company_inn": "7701158817"},
    )
    assert resp.status_code == 400


def test_person_report_sboy_always_503(client: TestClient) -> None:
    resp = client.post(
        "/bki/person-report",
        json={"last_name": "Сбоев", "first_name": "Семён", "company_inn": "7705729405", **_CONSENT},
    )
    assert resp.status_code == 503


def test_chaos_reaches_new_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_FAILURE_RATE", "1")
    chaotic = TestClient(app)
    assert chaotic.get("/gir-bo/7701158817").status_code == 503
    assert chaotic.get("/kontur/7701158817").status_code == 503
