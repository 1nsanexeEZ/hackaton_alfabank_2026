"""Настройки сервиса из переменных окружения (префикс MOCK_)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    latency_ms_min: int
    latency_ms_max: int
    failure_rate: float
    bki_always_fail_inns: frozenset[str]


def get_settings() -> Settings:
    """Читает окружение при каждом вызове — чтобы тесты могли переопределить задержки и сбои."""
    raw_fail = os.getenv("MOCK_BKI_ALWAYS_FAIL_INNS", "7705729405")
    fail_inns = frozenset(part.strip() for part in raw_fail.split(",") if part.strip())
    return Settings(
        latency_ms_min=int(os.getenv("MOCK_LATENCY_MS_MIN", "200")),
        latency_ms_max=int(os.getenv("MOCK_LATENCY_MS_MAX", "1500")),
        failure_rate=float(os.getenv("MOCK_FAILURE_RATE", "0.1")),
        bki_always_fail_inns=fail_inns,
    )
