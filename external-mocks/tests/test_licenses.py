from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_INNS


def test_licensed_activity_has_a_license(client: TestClient) -> None:
    """Основной вид деятельности лицензируется — у компании есть действующая лицензия."""
    inn = next(
        inn
        for inn in (f"77070831{n:02d}" for n in range(100))
        if client.get(f"/egrul/{inn}").status_code == 200
        and client.get(f"/egrul/{inn}").json()["ОКВЭДОсн"]["Код"] == "86.10"
    )
    [license_] = client.get(f"/licenses/{inn}").json()["Лицензии"]
    assert license_["ВидДеятельности"] == "Медицинская деятельность"
    assert license_["ОКВЭД"] == "86.10" and license_["Статус"] == "ДЕЙСТВУЕТ"


def test_clinic_without_a_license(client: TestClient) -> None:
    assert client.get("/egrul/7707115143").json()["ОКВЭДОсн"]["Код"] == "86.10"
    assert client.get("/licenses/7707115143").json() == {"ИНН": "7707115143", "Лицензии": []}


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_demo_companies_need_no_license(client: TestClient, inn: str) -> None:
    assert client.get(f"/licenses/{inn}").json()["Лицензии"] == []


def test_unknown_inn_404(client: TestClient) -> None:
    assert client.get("/licenses/1234567890").status_code == 404
