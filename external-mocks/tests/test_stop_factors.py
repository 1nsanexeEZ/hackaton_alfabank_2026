"""Компании для стоп-факторов общей схемы (STOP_DEMO): реорганизация, исключение из реестра,
недостоверность сведений, массовый руководитель, стоп-лист банка."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.data import STOP_DEMO
from app.inn import validate_inn
from tests.conftest import DEMO_INNS


def test_stop_demo_inns_are_valid() -> None:
    assert len(STOP_DEMO) == 5
    assert all(validate_inn(inn) for inn in STOP_DEMO)


@pytest.mark.parametrize(
    ("inn", "status"), [("7707146014", "REORGANIZING"), ("7707146021", "EXCLUDED")]
)
def test_registry_status(client: TestClient, inn: str, status: str) -> None:
    assert client.get(f"/egrul/{inn}").json()["Статус"]["Код"] == status


def test_unreliable_records(client: TestClient) -> None:
    body = client.get("/egrul/7707146039").json()
    assert [r["Сведения"] for r in body["СведНедостоверн"]] == ["Адрес", "Руководитель"]


def test_mass_head(client: TestClient) -> None:
    assert client.get("/fns/7707146046").json()["mass_head"] is True


def test_bank_stop_list(client: TestClient) -> None:
    body = client.get("/abs/stop-list/7707146053").json()
    assert body["listed"] is True and body["reason"]
    assert body["listed_at"]


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_demo_companies_are_clean(client: TestClient, inn: str) -> None:
    """Демо S-1…S-9: новых стоп-факторов нет, их исходы не меняются."""
    assert client.get(f"/egrul/{inn}").json()["СведНедостоверн"] == []
    assert client.get(f"/fns/{inn}").json()["mass_head"] is False
    stop = client.get(f"/abs/stop-list/{inn}").json()
    assert stop == {"inn": inn, "listed": False, "reason": None, "listed_at": None}


def test_stop_list_invalid_inn_404(client: TestClient) -> None:
    assert client.get("/abs/stop-list/1234567890").status_code == 404
