from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_INNS

_M = 100_000_000  # миллион рублей в копейках


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_fns_demo_shape(client: TestClient, inn: str) -> None:
    body = client.get(f"/fns/{inn}").json()
    assert body["inn"] == inn
    for key in ("arrears_kop", "revenue_kop", "expenses_kop", "avg_headcount", "report_year"):
        assert key in body
    assert isinstance(body["msp_registry"], bool)


def test_fns_zakat_has_arrears(client: TestClient) -> None:
    assert client.get("/fns/7703417070").json()["arrears_kop"] == 350_000 * 100


def test_fns_progress_revenue_contradicts_declared(client: TestClient) -> None:
    # ФНС даёт 12 млн против заявленных клиентом 36 млн — это основа сценария S-5.
    assert client.get("/fns/7704568152").json()["revenue_kop"] == 12 * _M


def test_fns_invalid_inn_404(client: TestClient) -> None:
    assert client.get("/fns/1234567890").status_code == 404
