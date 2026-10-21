from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_INNS

_STATUSES = {"ACTIVE", "LIQUIDATING", "LIQUIDATED", "BANKRUPT"}


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_egrul_demo_shape(client: TestClient, inn: str) -> None:
    resp = client.get(f"/egrul/{inn}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ИНН"] == inn
    assert body["Статус"]["Код"] in _STATUSES
    assert body["ОрганизационнаяФорма"] in {"ООО", "АО", "ИП"}
    assert "Код" in body["ОКВЭДОсн"]
    assert "ФИО" in body["Руководитель"]


def test_egrul_zakat_is_liquidating(client: TestClient) -> None:
    assert client.get("/egrul/7703417070").json()["Статус"]["Код"] == "LIQUIDATING"


def test_egrul_vector_head_differs_from_declared(client: TestClient) -> None:
    body = client.get("/egrul/7702987976").json()
    assert body["Руководитель"]["ФИО"] == "Сидоров Сергей Сергеевич"


def test_egrul_ip_has_no_kpp(client: TestClient) -> None:
    body = client.get("/egrul/770669871605").json()
    assert body["ОрганизационнаяФорма"] == "ИП"
    assert "КПП" not in body


def test_egrul_llc_has_kpp(client: TestClient) -> None:
    assert client.get("/egrul/7701158817").json()["КПП"] == "770101001"


def test_egrul_invalid_inn_404(client: TestClient) -> None:
    assert client.get("/egrul/1234567890").status_code == 404
