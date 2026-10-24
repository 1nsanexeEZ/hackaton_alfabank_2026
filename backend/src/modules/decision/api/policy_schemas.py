"""Схемы ручек версий кредитной политики."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.decision.application.policy_versions import (
    OutcomeShift,
    PolicyCatalog,
    Preview,
    PreviewItem,
    Verdict,
)
from src.modules.decision.domain.model import Grade, Outcome
from src.modules.decision.domain.policy_version import PolicyStatus, PolicyVersion


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PolicyVersionSummaryRead(_Read):
    version: str = Field(description="`policy_v10` — встроенная, `policy_v10.1`… — админа")
    status: PolicyStatus = Field(
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


class PolicyVersionRead(PolicyVersionSummaryRead):
    body: dict[str, Any] = Field(
        description="Документ политики, как policy_v10.yaml: стоп-факторы, лимиты, "
        "ценообразование, маршрутизация, стратегия (мягкие триггеры, матрица грейд × сумма, "
        "зоны двух моделей), требования закона; Decimal — строками"
    )

    @classmethod
    def of(cls, version: PolicyVersion) -> PolicyVersionRead:
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


class CodeNameRead(_Read):
    code: str
    name: str = Field(description="Как это называется в тексте для клиента")


class PolicyReasonRead(_Read):
    code: str
    text: str = Field(description="Что клиент увидит в решении")
    hint: str | None = Field(description="Что клиент может сделать")


class PolicyCatalogRead(_Read):
    builtin: str = Field(description="Код встроенной политики")
    legacy_scale: list[Grade] = Field(description="Шкала `grades` scorecard_v1")
    pd_scale: list[Grade] = Field(
        description="Шкала `grades` PD-модели; зоны двух моделей покрывают её всегда"
    )
    outcomes: list[CodeNameRead] = Field(description="Исходы решения с текстом для клиента")
    reasons: list[PolicyReasonRead] = Field(
        description="Коды причин с текстами из explanations_ru.yaml; только их можно ставить в "
        "`stop_factors.registry_statuses` и `routing.flags`, тексты здесь не правятся"
    )
    stop_factors: list[str] = Field(description="Ключи раздела `stop_factors`")
    registry_statuses: list[str] = Field(
        description="Статусы ЕГРЮЛ — ключи `stop_factors.registry_statuses`"
    )
    routing_flags: list[str] = Field(description="Ключи `routing.flags` в порядке проверки")
    zones: list[str] = Field(description="Зоны `strategy.two_models`")
    zone_verdicts: list[str] = Field(description="Клетки матрицы `strategy.two_models.matrix`")
    zsk_levels: list[str] = Field(description="Уровни ЗСК `compliance.aml`")
    legal_forms: list[str] = Field(
        description="Формы `compliance.automated_decision_consent.legal_forms`"
    )
    collateral_types: list[CodeNameRead] = Field(description="Виды залога — ключи `limits.ltv`")
    products: list[CodeNameRead] = Field(
        description="Продукты, которые можно назвать в `alternatives`"
    )

    @classmethod
    def of(cls, catalog: PolicyCatalog) -> PolicyCatalogRead:
        return cls.model_validate(catalog)


class VerdictRead(_Read):
    outcome: Outcome
    reason_codes: list[str]
    policy_version: str


class PolicyPreviewItemRead(_Read):
    application_id: UUID
    result_id: UUID = Field(description="Сохранённое автоматическое решение")
    decided_at: datetime
    before: VerdictRead = Field(description="Как решено тогда своей версией политики")
    after: VerdictRead = Field(
        description="Как решила бы примеряемая версия на текущих данных заявки"
    )


class OutcomeShiftRead(BaseModel):
    """Клетка матрицы переходов: столько заявок было с исходом `from` и стало с `to`."""

    from_outcome: Outcome = Field(alias="from")
    to_outcome: Outcome = Field(alias="to")
    count: int

    @classmethod
    def of(cls, shift: OutcomeShift) -> OutcomeShiftRead:
        return cls.model_validate(
            {"from": shift.from_outcome, "to": shift.to_outcome, "count": shift.count}
        )


class PolicyPreviewRead(BaseModel):
    version: str
    total: int = Field(description="Сколько заявок решено заново")
    changed: int = Field(description="Другой исход или другие коды причин")
    outcome_changed: int = Field(description="Другой исход")
    skipped: int = Field(description="Вход не собрать (заявки или продукта уже нет) — пропущена")
    transitions: list[OutcomeShiftRead] = Field(
        description="Переходы исходов «было → стало», только непустые"
    )
    items: list[PolicyPreviewItemRead]

    @classmethod
    def of(cls, preview: Preview) -> PolicyPreviewRead:
        return cls(
            version=preview.version,
            total=len(preview.items),
            changed=preview.changed,
            outcome_changed=preview.outcome_changed,
            skipped=preview.skipped,
            transitions=[OutcomeShiftRead.of(s) for s in preview.transitions],
            items=[_item(i) for i in preview.items],
        )


def _item(item: PreviewItem) -> PolicyPreviewItemRead:
    return PolicyPreviewItemRead(
        application_id=item.application_id,
        result_id=item.result_id,
        decided_at=item.decided_at,
        before=_verdict(item.before),
        after=_verdict(item.after),
    )


def _verdict(verdict: Verdict) -> VerdictRead:
    return VerdictRead.model_validate(verdict)
