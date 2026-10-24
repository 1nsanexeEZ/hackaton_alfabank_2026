"""Порты scoring: модель, репозиторий результатов, версии PD-модели и хранилище признаков
клиента. Соседние модули (applications, enrichment) scoring читает через их фасады напрямую
в use case."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from src.modules.scoring.domain.client_features import FeatureSnapshot
from src.modules.scoring.domain.model import MlScore, ScoringInput, ScoringResult
from src.modules.scoring.domain.model_version import ModelVersion
from src.modules.scoring.domain.quality import DataQuality
from src.modules.scoring.domain.scorecard import ScorecardOutput


class ScoringModel(Protocol):
    """Действующая PD-модель или scorecard_v1 (для её golden-тестов и воспроизведения)."""

    @property
    def version(self) -> str: ...

    def calculate(self, inp: ScoringInput) -> ScorecardOutput: ...


class MlScoringModel(Protocol):
    """ML-модель: считается рядом с PD-моделью на том же входе."""

    @property
    def version(self) -> str: ...

    def predict(self, inp: ScoringInput) -> MlScore: ...


class DataQualityAssessor(Protocol):
    """«Данные полные?»: какие источники не ответили и сколько признаков без данных."""

    def assess(self, sources_failed: Sequence[str], completeness: Decimal) -> DataQuality: ...


class ScoringRepository(Protocol):
    async def add(self, result: ScoringResult, *, input_snapshot: dict[str, Any]) -> None: ...

    async def get_by_command(self, command_event_id: UUID) -> ScoringResult | None: ...

    async def latest_for_application(self, application_id: UUID) -> ScoringResult | None: ...


class ScoringHistory(Protocol):
    """Прошлые результаты PD-модели со снимками входа — для примерки версии модели."""

    async def recent_pd_inputs(self, limit: int) -> list[tuple[ScoringResult, dict[str, Any]]]:
        """Последний результат по каждой из `limit` самых свежих заявок; только с PD."""
        ...


class ModelVersionRepository(Protocol):
    """Версии PD-модели админа (`scoring_model_versions`); встроенной здесь нет."""

    async def list_all(self) -> list[ModelVersion]: ...

    async def get(self, version: str) -> ModelVersion | None: ...

    async def codes(self) -> list[str]: ...

    async def active_version(self) -> str | None:
        """Код активной версии — один короткий запрос на команду; None — действует встроенная."""
        ...

    async def add(self, version: ModelVersion) -> None: ...

    async def save(self, version: ModelVersion) -> None: ...

    async def delete(self, version: str) -> None: ...


class FeatureSnapshotRepository(Protocol):
    """Хранилище признаков клиента."""

    async def add(self, snapshot: FeatureSnapshot) -> None: ...

    async def get_by_enrichment_snapshot(self, snapshot_id: UUID) -> FeatureSnapshot | None: ...

    async def latest(self, organization_id: UUID, *, since: date) -> FeatureSnapshot | None:
        """Самый свежий по данным снимок компании с `as_of` не раньше `since`."""
        ...
