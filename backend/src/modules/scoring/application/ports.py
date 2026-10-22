"""Порты scoring: модель и репозиторий результатов. Соседние модули (applications,
enrichment) scoring читает через их фасады напрямую в use case."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from src.modules.scoring.domain.model import ScoringInput, ScoringResult
from src.modules.scoring.domain.scorecard import ScorecardOutput


class ScoringModel(Protocol):
    """Действующая PD-модель или scorecard_v1 (для её golden-тестов и воспроизведения)."""

    @property
    def version(self) -> str: ...

    def calculate(self, inp: ScoringInput) -> ScorecardOutput: ...


class ScoringRepository(Protocol):
    async def add(self, result: ScoringResult, *, input_snapshot: dict[str, Any]) -> None: ...

    async def get_by_command(self, command_event_id: UUID) -> ScoringResult | None: ...

    async def latest_for_application(self, application_id: UUID) -> ScoringResult | None: ...
