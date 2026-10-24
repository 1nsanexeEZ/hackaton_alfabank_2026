"""Версии PD-модели: реестр для админа, активная модель для расчёта и примерка черновика.

- реестр — встроенная модель из YAML (только читается) и версии админа из БД. Черновик — клон
  любой версии; править и удалять можно только черновик; активировать — черновик или архивную
  версию (откат), прежняя активная уходит в архив. «Вернуть встроенную» — активировать её:
  активная версия из БД уходит в архив;
- активная модель (`ActiveModelProvider`) — на каждую команду один запрос «какая версия
  активна»; собранные модели кэшируются в процессе по коду версии: активная и архивная версии
  неизменны, так что кэш не протухает, а API и консьюмеры видят одно и то же через БД;
- примерка — последние результаты PD-модели пересчитываются версией-кандидатом по сохранённому
  `input_snapshot`, ничего не пишется. Результаты scorecard_v1 (без PD, шкала A–E) не берутся:
  их грейд с A–J не сравнить.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import InvalidStatusTransitionError, NotFoundError
from src.modules.scoring.application.ports import (
    ModelVersionRepository,
    ScoringHistory,
    ScoringModel,
)
from src.modules.scoring.application.serialization import load_input
from src.modules.scoring.domain.model import Grade, Segment
from src.modules.scoring.domain.model_version import (
    GRADE_ORDER,
    ModelVersion,
    base_of,
    next_version,
)

FeatureKind = Literal["numeric", "categorical"]


@dataclass(frozen=True, slots=True)
class FeatureInfo:
    code: str
    kind: FeatureKind  # числовой — интервальные бины, категориальный — бины категорий
    categories: tuple[str, ...]  # категории, у каждой из которых обязан быть бин
    required: bool  # обязателен в скоркарте каждого сегмента


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Из чего собирается документ модели — для редактора."""

    builtin: str
    segments: tuple[Segment, ...]
    features: tuple[FeatureInfo, ...]
    grades: tuple[Grade, ...]  # грейды с верхней границей PD, по возрастанию
    worst_grade: Grade  # PD выше границы последнего грейда
    industry_sections: tuple[str, ...]  # обязательные секции отраслевого риска


class ModelDocuments(Protocol):
    """Документ PD-модели (тот же, что YAML): встроенная модель, проверка и сборка. Документ не
    прошёл проверку — `ValidationError` (422) со списком `{path, message}`."""

    @property
    def builtin_version(self) -> str: ...

    def builtin_body(self) -> dict[str, Any]: ...

    def builtin_model(self) -> ScoringModel: ...

    def normalize(self, body: Mapping[str, Any], version: str) -> dict[str, Any]: ...

    def compile(self, body: Mapping[str, Any], version: str) -> ScoringModel: ...

    def catalog(self) -> ModelCatalog: ...


@dataclass(frozen=True, slots=True)
class Estimate:
    score: int
    pd_12m: Decimal | None
    grade: Grade
    segment: Segment | None
    model_version: str


@dataclass(frozen=True, slots=True)
class PreviewItem:
    application_id: UUID
    result_id: UUID
    computed_at: datetime
    before: Estimate  # как посчитано тогда — своей версией модели
    after: Estimate  # как посчитала бы версия-кандидат


@dataclass(frozen=True, slots=True)
class GradeShift:
    from_grade: Grade
    to_grade: Grade
    count: int


@dataclass(frozen=True, slots=True)
class Preview:
    version: str
    items: tuple[PreviewItem, ...]
    transitions: tuple[GradeShift, ...]  # матрица переходов грейдов, только непустые клетки
    same: int
    better: int
    worse: int
    skipped: int  # снимок входа не прочитать (старый формат) — пропущен


class ModelProvider(Protocol):
    """Какой моделью считать сейчас."""

    async def active(self, versions: ModelVersionRepository) -> ScoringModel: ...


class FixedModel:
    """Всегда одна и та же модель, БД не спрашивает: тесты и golden."""

    def __init__(self, model: ScoringModel) -> None:
        self._model = model

    async def active(self, versions: ModelVersionRepository) -> ScoringModel:
        return self._model


class ActiveModelProvider:
    """Активная версия админа или, если её нет, встроенная модель."""

    def __init__(self, documents: ModelDocuments) -> None:
        self._documents = documents
        self._compiled: dict[str, ScoringModel] = {}

    async def active(self, versions: ModelVersionRepository) -> ScoringModel:
        code = await versions.active_version()
        if code is None:
            return self._documents.builtin_model()
        model = self._compiled.get(code)
        if model is None:
            version = await versions.get(code)
            if version is None:  # активную версию не удалить — сюда не попасть
                raise RuntimeError(f"active model version {code!r} is gone")
            model = self._documents.compile(version.body, version.version)
            self._compiled[code] = model
        return model


class ModelVersions:
    """Реестр версий PD-модели для админки."""

    def __init__(
        self, repository: ModelVersionRepository, documents: ModelDocuments, clock: Clock
    ) -> None:
        self._repository = repository
        self._documents = documents
        self._clock = clock

    def catalog(self) -> ModelCatalog:
        return self._documents.catalog()

    async def list_all(self) -> list[ModelVersion]:
        """Встроенная первой, затем версии админа в порядке создания."""
        stored = await self._repository.list_all()
        overridden = any(v.status == "active" for v in stored)
        return [self._builtin(overridden=overridden), *stored]

    async def get(self, version: str) -> ModelVersion:
        if version == self._documents.builtin_version:
            return self._builtin(overridden=await self._repository.active_version() is not None)
        found = await self._repository.get(version)
        if found is None:
            raise NotFoundError("Model version not found", details={"version": version})
        return found

    async def create_draft(self, based_on: str, comment: str | None, by: UUID) -> ModelVersion:
        """Черновик — копия любой версии под следующим номером `<встроенная>.<n>`."""
        source = await self.get(based_on)
        code = next_version(base_of(source.version), await self._repository.codes())
        draft = ModelVersion.draft(
            code,
            self._body(source.body, code),
            based_on=source.version,
            comment=comment,
            by=by,
            now=self._clock.now(),
        )
        await self._repository.add(draft)
        return draft

    async def update_draft(
        self, version: str, body: Mapping[str, Any], comment: str | None
    ) -> ModelVersion:
        draft = await self.get(version)
        draft.ensure_draft("update")
        draft.edit(self._body(body, draft.version), comment, self._clock.now())
        await self._repository.save(draft)
        return draft

    async def delete_draft(self, version: str) -> None:
        draft = await self.get(version)
        draft.ensure_draft("delete")
        await self._repository.delete(draft.version)

    async def activate(self, version: str, by: UUID) -> ModelVersion:
        """Черновик или архивная версия становится активной, прежняя активная — архивной.
        Встроенная модель «активируется» тем, что активная версия из БД уходит в архив."""
        target = await self.get(version)
        now = self._clock.now()
        current = await self._current()
        if target.builtin:
            if current is None:
                raise InvalidStatusTransitionError(
                    details={"version": target.version, "from": "active", "to": "active"}
                )
            current.archive(now)
            await self._repository.save(current)
            return self._builtin(overridden=False)
        target.activate(by, now)
        # Сначала архив, потом новая активная: активной в БД бывает только одна (индекс).
        if current is not None:
            current.archive(now)
            await self._repository.save(current)
        await self._repository.save(target)
        return target

    async def preview(self, version: str, limit: int, history: ScoringHistory) -> Preview:
        """Пересчёт последних заявок версией-кандидатом, без записи."""
        candidate = await self.get(version)
        model = (
            self._documents.builtin_model()
            if candidate.builtin
            else self._documents.compile(candidate.body, candidate.version)
        )
        items: list[PreviewItem] = []
        skipped = 0
        for result, snapshot in await history.recent_pd_inputs(limit):
            try:
                scoring_input = load_input(snapshot)
            except (KeyError, TypeError, ValueError, ArithmeticError):
                skipped += 1
                continue
            output = model.calculate(scoring_input)
            items.append(
                PreviewItem(
                    application_id=result.application_id,
                    result_id=result.id,
                    computed_at=result.computed_at,
                    before=Estimate(
                        result.score,
                        result.pd_12m,
                        result.grade,
                        result.segment,
                        result.model_version,
                    ),
                    after=Estimate(
                        output.score, output.pd_12m, output.grade, output.segment, model.version
                    ),
                )
            )
        return _summary(candidate.version, items, skipped)

    async def _current(self) -> ModelVersion | None:
        code = await self._repository.active_version()
        return None if code is None else await self._repository.get(code)

    def _builtin(self, *, overridden: bool) -> ModelVersion:
        return ModelVersion(
            version=self._documents.builtin_version,
            status="archived" if overridden else "active",
            body=self._documents.builtin_body(),
            builtin=True,
        )

    def _body(self, body: Mapping[str, Any], version: str) -> dict[str, Any]:
        """Код версии внутри документа — всегда код самой версии: он пишется в результаты."""
        return self._documents.normalize({**body, "version": version}, version)


def _summary(version: str, items: list[PreviewItem], skipped: int) -> Preview:
    shifts = Counter((item.before.grade, item.after.grade) for item in items)
    moves = [
        GRADE_ORDER.index(item.after.grade) - GRADE_ORDER.index(item.before.grade) for item in items
    ]
    return Preview(
        version=version,
        items=tuple(items),
        transitions=tuple(
            GradeShift(before, after, count)
            for (before, after), count in sorted(
                shifts.items(),
                key=lambda shift: (GRADE_ORDER.index(shift[0][0]), GRADE_ORDER.index(shift[0][1])),
            )
        ),
        same=sum(1 for move in moves if move == 0),
        better=sum(1 for move in moves if move < 0),
        worse=sum(1 for move in moves if move > 0),
        skipped=skipped,
    )
