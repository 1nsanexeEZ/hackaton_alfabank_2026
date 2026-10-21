from __future__ import annotations

from fastapi.testclient import TestClient


def test_abs_disbursement_simulated(client: TestClient) -> None:
    resp = client.post(
        "/abs/disbursements",
        json={
            "application_id": "app-1",
            "account": "40702810000000000001",
            "amount_kop": 300_000_000,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulated"] is True
    assert body["status"] == "executed"
    assert body["operation_id"]


def test_edo_sign_simulated(client: TestClient) -> None:
    resp = client.post(
        "/edo/sign", json={"document_hash": "abc123", "signer": "owner@romashka.test"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulated"] is True
    assert body["signature_id"]
    assert body["signed_at"]
