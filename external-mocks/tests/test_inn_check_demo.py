"""Компании для проверки по ИНН до заявки (CHECK_DEMO): банкротство, массовый адрес, долги;
валидный ИНН, которого нет в реестре (UNREGISTERED)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.data import CHECK_DEMO, UNREGISTERED
from app.inn import validate_inn


def test_check_demo_inns_are_valid() -> None:
    assert len(CHECK_DEMO) == 3
    assert all(validate_inn(inn) for inn in (*CHECK_DEMO, *UNREGISTERED))


def test_bankrupt(client: TestClient) -> None:
    assert client.get("/egrul/7707177012").json()["Статус"]["Код"] == "BANKRUPT"
    kontur = client.get("/kontur/7707177012").json()
    assert kontur["reliability"] == "red"
    [message] = kontur["bankruptcy_messages"]
    assert message["case"] == "А40-117701/2026"


def test_mass_address(client: TestClient) -> None:
    egrul = client.get("/egrul/7707177020").json()
    assert egrul["МассовыйАдрес"] is True and egrul["Статус"]["Код"] == "ACTIVE"


def test_debts(client: TestClient) -> None:
    assert client.get("/egrul/7707177037").json()["Статус"]["Код"] == "ACTIVE"
    fns = client.get("/fns/7707177037").json()
    assert fns["arrears_kop"] == 124_000_000 and fns["account_blocks"] == []
    kontur = client.get("/kontur/7707177037").json()
    assert kontur["enforcement_proceedings"] == {"active": 3, "sum_rub": 1_860_000}
    assert kontur["bankruptcy_messages"] == []


@pytest.mark.parametrize("path", ["/egrul", "/fns", "/kontur", "/abs/stop-list"])
def test_unregistered_inn_is_not_found(client: TestClient, path: str) -> None:
    [inn] = UNREGISTERED
    assert client.get(f"{path}/{inn}").status_code == 404
