from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

DEMO_INNS = [
    "7701158817",  # Ромашка
    "770669871605",  # ИП Иванов
    "7702987976",  # Вектор
    "7703417070",  # Закат
    "7704568152",  # Прогресс
    "7705729405",  # Сбой
]


@pytest.fixture(autouse=True)
def _no_chaos(monkeypatch: pytest.MonkeyPatch) -> None:
    # В тестах отключаем задержки и случайные сбои (их читает get_settings на каждый запрос).
    monkeypatch.setenv("MOCK_FAILURE_RATE", "0")
    monkeypatch.setenv("MOCK_LATENCY_MS_MIN", "0")
    monkeypatch.setenv("MOCK_LATENCY_MS_MAX", "0")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
