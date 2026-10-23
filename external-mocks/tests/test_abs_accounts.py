"""АБС: клиент банка с какой даты и помесячные обороты по расчётному счёту."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_INNS


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_demo_turnover_follows_revenue(client: TestClient, inn: str) -> None:
    body = client.get(f"/abs/accounts/{inn}").json()
    fns = client.get(f"/fns/{inn}").json()
    egrul = client.get(f"/egrul/{inn}").json()
    assert body["client_since"] == egrul["ДатаРег"]  # счёт открыт при регистрации
    months = body["turnover"]
    assert 0 < len(months) <= 24
    assert [m["month"] for m in months] == sorted(m["month"] for m in months)
    assert months[-1]["month"] < date.today().strftime("%Y-%m")  # без текущего месяца
    monthly = fns["revenue_kop"] / 12
    assert all(0.9 * monthly <= m["credit_kop"] <= 1.1 * monthly for m in months)


def test_young_company_has_short_history(client: TestClient) -> None:
    """Стартап «Новый старт» младше года — оборотов меньше 24 месяцев."""
    young = [
        inn for inn in DEMO_INNS if len(client.get(f"/abs/accounts/{inn}").json()["turnover"]) < 24
    ]
    assert young


def test_deterministic(client: TestClient) -> None:
    first = client.get("/abs/accounts/7701158817").json()
    assert client.get("/abs/accounts/7701158817").json() == first


def test_some_generated_companies_moved_to_the_bank_recently(client: TestClient) -> None:
    def valid(base: int) -> str:
        digits = [int(d) for d in f"{base:09d}"]
        weights = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        return f"{base:09d}{sum(d * w for d, w in zip(digits, weights, strict=True)) % 11 % 10}"

    bodies = [client.get(f"/abs/accounts/{valid(770200000 + n)}").json() for n in range(80)]
    egruls = [client.get(f"/egrul/{b['inn']}").json() for b in bodies]
    moved = [b for b, e in zip(bodies, egruls, strict=True) if b["client_since"] > e["ДатаРег"]]
    assert moved and len(moved) < len(bodies)
    assert all(len(b["turnover"]) <= 6 for b in moved)


def test_invalid_inn_404(client: TestClient) -> None:
    assert client.get("/abs/accounts/1234567890").status_code == 404
