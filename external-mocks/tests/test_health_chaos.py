from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_bypasses_chaos(monkeypatch: pytest.MonkeyPatch) -> None:
    # Даже при гарантированном сбое /health обязан отвечать 200 — на нём Docker healthcheck.
    monkeypatch.setenv("MOCK_FAILURE_RATE", "1")
    monkeypatch.setenv("MOCK_LATENCY_MS_MIN", "0")
    monkeypatch.setenv("MOCK_LATENCY_MS_MAX", "0")
    assert TestClient(app).get("/health").status_code == 200


def test_chaos_can_fail_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_FAILURE_RATE", "1")
    monkeypatch.setenv("MOCK_LATENCY_MS_MIN", "0")
    monkeypatch.setenv("MOCK_LATENCY_MS_MAX", "0")
    assert TestClient(app).get("/egrul/7701158817").status_code == 503
