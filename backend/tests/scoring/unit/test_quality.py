"""«Данные полные?»: критичный источник не ответил или мало признаков с данными → degraded.
Пороги — в `quality_v1.yaml`, битый файл — приложение не стартует."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.scoring.domain.quality import DataQuality
from src.modules.scoring.infrastructure.config_loader import (
    ScorecardConfigError,
    default_quality,
    load_quality_file,
)

POLICY = default_quality()


def test_config() -> None:
    assert POLICY.version == "quality_v1"
    assert POLICY.critical_sources == frozenset({"fns", "bki"})
    assert POLICY.min_completeness == Decimal("0.7")


def test_complete_data_is_ok() -> None:
    assert POLICY.assess((), Decimal("1.000")) == DataQuality("ok")


def test_non_critical_source_does_not_degrade() -> None:
    """ГИР БО, Контур, БКИ руководителя — для стоп-факторов и маршрутов решения, не для модели."""
    assert POLICY.assess(("gir_bo", "kontur", "bki_head"), Decimal("0.9")).level == "ok"


def test_critical_source_degrades_once() -> None:
    quality = POLICY.assess(("bki", "kontur", "bki"), Decimal("0.9"))
    assert quality == DataQuality("degraded", ("source_failed:bki",))


@pytest.mark.parametrize(
    ("completeness", "level"),
    [("0.700", "ok"), ("0.699", "degraded")],
)
def test_completeness_threshold(completeness: str, level: str) -> None:
    quality = POLICY.assess((), Decimal(completeness))
    assert quality.level == level
    if level == "degraded":
        assert quality.reasons == (f"completeness_below:{completeness}",)


def test_both_reasons_are_kept() -> None:
    quality = POLICY.assess(("fns",), Decimal("0.5"))
    assert quality.reasons == ("source_failed:fns", "completeness_below:0.5")


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("version: q\ncritical_sources: [cbr]\nmin_completeness: '0.7'\n", "неизвестные источники"),
        ("version: q\ncritical_sources: []\nmin_completeness: '1.5'\n", "не прошло схему"),
        ("version: q\ncritical_sources: []\n", "не прошло схему"),
        ("version: q\ncritical_sources: []\nmin_completeness: '0.7'\nextra: 1\n", "не прошло"),
    ],
)
def test_broken_config_is_rejected(tmp_path: Path, text: str, error: str) -> None:
    path = tmp_path / "quality.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ScorecardConfigError, match=error):
        load_quality_file(path)
