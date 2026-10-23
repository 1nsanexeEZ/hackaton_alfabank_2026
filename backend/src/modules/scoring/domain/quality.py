"""Качество данных скоринга — развилка «Данные полные?» модели оценки PD общей схемы.

Модели считают всегда: пропуск — бин «нет данных», сбой источника не штрафует и не поощряет. Но
если не ответил источник, без которого оценке верить нельзя, или признаков без данных слишком
много, результат помечается `degraded`: решение по такой заявке принимает человек, а модели всё
равно посчитаны — андеррайтер видит обе оценки. Какие источники критичны и порог полноты — в YAML
(`quality_v1`), здесь — только логика. Чистая функция: без IO и без `now()`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

QualityLevel = Literal["ok", "degraded"]


@dataclass(frozen=True, slots=True)
class DataQuality:
    level: QualityLevel
    # Почему degraded: `source_failed:<источник>`, `completeness_below:<полнота>`.
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    version: str
    critical_sources: frozenset[str]
    min_completeness: Decimal  # доля признаков с данными строго меньше — degraded

    def assess(self, sources_failed: Sequence[str], completeness: Decimal) -> DataQuality:
        reasons = [
            f"source_failed:{source}"
            for source in dict.fromkeys(sources_failed)
            if source in self.critical_sources
        ]
        if completeness < self.min_completeness:
            reasons.append(f"completeness_below:{completeness}")
        return DataQuality("degraded" if reasons else "ok", tuple(reasons))
