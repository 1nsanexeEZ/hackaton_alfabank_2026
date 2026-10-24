"""Схемы ручек версий PD-модели."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.scoring.application.model_versions import (
    Estimate,
    GradeShift,
    ModelCatalog,
    Preview,
    PreviewItem,
)
from src.modules.scoring.domain.model import Grade, Segment
from src.modules.scoring.domain.model_version import ModelStatus, ModelVersion


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ModelVersionSummaryRead(_Read):
    version: str = Field(description="`pd_model_v2` — встроенная, `pd_model_v2.1`… — админа")
    status: ModelStatus = Field(
        description="draft — черновик, active — действует, archived — в архиве. Встроенная "
        "active, пока ни одна версия админа не активна, иначе archived"
    )
    builtin: bool = Field(description="Встроенная из YAML: только читается")
    based_on: str | None = None
    comment: str | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    activated_by: UUID | None = None
    activated_at: datetime | None = None


class ModelVersionRead(ModelVersionSummaryRead):
    body: dict[str, Any] = Field(
        description="Документ модели, как pd_model_v2.yaml: сегменты, признаки, бины, WoE и "
        "баллы, калибровка, границы грейдов; Decimal — строками"
    )

    @classmethod
    def of(cls, version: ModelVersion) -> ModelVersionRead:
        return cls.model_validate(version)


class DraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    based_on: str = Field(min_length=1, max_length=32, description="Версия, которую копируем")
    comment: str | None = Field(default=None, max_length=2000)


class DraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: dict[str, Any] = Field(
        description="Документ целиком; `version` внутри заменяется кодом версии"
    )
    comment: str | None = Field(
        default=None, max_length=2000, description="Не прислали — остаётся прежний"
    )


class FeatureInfoRead(_Read):
    code: str
    kind: Literal["numeric", "categorical"] = Field(
        description="numeric — интервальные бины [from; to), categorical — бины категорий"
    )
    categories: list[str] = Field(description="Категории, у каждой из которых обязан быть бин")
    required: bool = Field(description="Обязателен в скоркарте каждого сегмента")


class ModelCatalogRead(_Read):
    builtin: str = Field(description="Код встроенной модели")
    segments: list[Segment] = Field(description="Скоркарта нужна каждому сегменту")
    features: list[FeatureInfoRead]
    grades: list[Grade] = Field(description="Грейды с верхней границей PD, по возрастанию")
    worst_grade: Grade = Field(description="PD не ниже границы последнего грейда")
    industry_sections: list[str] = Field(description="Обязательные секции `industry_sections`")

    @classmethod
    def of(cls, catalog: ModelCatalog) -> ModelCatalogRead:
        return cls.model_validate(catalog)


class EstimateRead(_Read):
    score: int
    pd_12m: Decimal | None
    grade: Grade
    segment: Segment | None
    model_version: str


class PreviewItemRead(_Read):
    application_id: UUID
    result_id: UUID
    computed_at: datetime
    before: EstimateRead = Field(description="Как посчитано тогда своей версией модели")
    after: EstimateRead = Field(description="Как посчитала бы примеряемая версия")


class GradeShiftRead(BaseModel):
    """Клетка матрицы переходов: столько заявок было в грейде `from` и стало в `to`."""

    from_grade: Grade = Field(alias="from")
    to_grade: Grade = Field(alias="to")
    count: int

    @classmethod
    def of(cls, shift: GradeShift) -> GradeShiftRead:
        return cls.model_validate(
            {"from": shift.from_grade, "to": shift.to_grade, "count": shift.count}
        )


class PreviewRead(BaseModel):
    version: str
    total: int = Field(description="Сколько заявок пересчитано")
    same: int = Field(description="Грейд не изменился")
    better: int = Field(description="Грейд стал лучше")
    worse: int = Field(description="Грейд стал хуже")
    skipped: int = Field(description="Снимок входа не прочитан — заявка пропущена")
    transitions: list[GradeShiftRead] = Field(
        description="Переходы грейдов «было → стало», только непустые"
    )
    items: list[PreviewItemRead]

    @classmethod
    def of(cls, preview: Preview) -> PreviewRead:
        return cls(
            version=preview.version,
            total=len(preview.items),
            same=preview.same,
            better=preview.better,
            worse=preview.worse,
            skipped=preview.skipped,
            transitions=[GradeShiftRead.of(s) for s in preview.transitions],
            items=[_item(i) for i in preview.items],
        )


def _item(item: PreviewItem) -> PreviewItemRead:
    return PreviewItemRead(
        application_id=item.application_id,
        result_id=item.result_id,
        computed_at=item.computed_at,
        before=_estimate(item.before),
        after=_estimate(item.after),
    )


def _estimate(estimate: Estimate) -> EstimateRead:
    return EstimateRead.model_validate(estimate)
