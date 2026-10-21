from __future__ import annotations

from fastapi.testclient import TestClient

_CONSENT = {"consent_at": "2026-10-21T10:00:00+00:00", "request_id": "req-1"}


def test_bki_romashka_with_consent(client: TestClient) -> None:
    resp = client.post("/bki/report", json={"inn": "7701158817", **_CONSENT})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["obligations"]) == 1
    assert body["obligations"][0]["monthly_payment_kop"] == 180_000 * 100
    assert body["inquiries_30d"] == 1


def test_bki_without_consent_400(client: TestClient) -> None:
    resp = client.post("/bki/report", json={"inn": "7701158817", "request_id": "req-1"})
    assert resp.status_code == 400


def test_bki_sboy_always_503(client: TestClient) -> None:
    resp = client.post("/bki/report", json={"inn": "7705729405", **_CONSENT})
    assert resp.status_code == 503


def test_bki_ivanov_thin_file(client: TestClient) -> None:
    body = client.post("/bki/report", json={"inn": "770669871605", **_CONSENT}).json()
    assert body["obligations"] == []
    assert body["inquiries_30d"] == 0


def test_bki_zakat_overdue(client: TestClient) -> None:
    body = client.post("/bki/report", json={"inn": "7703417070", **_CONSENT}).json()
    assert body["obligations"][0]["max_overdue_days"] == 120


def test_bki_invalid_inn_404(client: TestClient) -> None:
    resp = client.post("/bki/report", json={"inn": "1234567890", **_CONSENT})
    assert resp.status_code == 404
