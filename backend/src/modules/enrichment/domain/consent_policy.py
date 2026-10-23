"""Кого не спрашиваем: БКИ — только с согласия субъекта (218-ФЗ), БКИ руководителя — только
с его личным согласием и если руководитель по реестру известен."""

from __future__ import annotations

from src.modules.enrichment.domain.enums import Source
from src.modules.enrichment.domain.snapshot import SourceError


def skip_reason(
    source: Source, *, bki_consent: bool, head_known: bool, head_consent: bool
) -> SourceError | None:
    """Источник не запрашиваем: нет согласия субъекта (218-ФЗ) или некого спрашивать."""
    if source == "bki" and not bki_consent:
        return SourceError("no_consent", "Нет согласия на запрос кредитной истории")
    if source == "bki_head":
        if not head_known:
            return SourceError("no_head", "Руководитель по реестру не найден среди участников")
        if not head_consent:
            return SourceError(
                "no_consent", "Нет согласия руководителя на запрос его кредитной истории"
            )
    return None
