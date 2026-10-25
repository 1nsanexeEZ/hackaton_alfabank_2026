"""Версии кредитной политики: реестр для админа, активная политика для решений и примерка.

- реестр — встроенная политика из YAML (только читается) и версии админа из БД. Черновик — клон
  любой версии; править и удалять можно только черновик; активировать — черновик или архивную
  версию (откат), прежняя активная уходит в архив. «Вернуть встроенную» — активировать её:
  активная версия из БД уходит в архив;
- активная политика (`ActivePolicyProvider`) — на каждую команду один запрос «какая версия
  активна»; собранные политики кэшируются в процессе по коду версии: активная и архивная версии
  неизменны, так что кэш не протухает, а API и консьюмеры видят одно и то же через БД;
- примерка — последние заявки с автоматическим решением решаются версией-кандидатом. Вход
  пересобирается `DecisionInputBuilder` на текущих данных соседей (заявка, снимок обогащения,
  последний результат скоринга, каталог продуктов), поэтому это примерка, а не точное
  воспроизведение: если данные с тех пор изменились, «после» отличается и без смены политики.
  Ничего не пишется.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import AppError, InvalidStatusTransitionError, NotFoundError
from src.modules.decision.application.input_builder import DecisionInputBuilder
from src.modules.decision.application.ports import DecisionHistory, PolicyVersionRepository
from src.modules.decision.domain.model import Grade, Outcome
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.domain.policy_version import (
    OUTCOME_ORDER,
    PolicyVersion,
    base_of,
    next_version,
)

logger = logging.getLogger(__name__)

# Вход примерки собирается под политику-кандидата: от неё зависят шкала грейдов, альтернативы и
# продукты стартапа.
InputBuilders = Callable[[CreditPolicy], DecisionInputBuilder]


@dataclass(frozen=True, slots=True)
class CodeName:
    code: str
    name: str  # текст для клиента из `explanations_ru.yaml`


@dataclass(frozen=True, slots=True)
class ReasonInfo:
    code: str
    text: str  # что клиент увидит в решении
    hint: str | None  # что можно сделать


@dataclass(frozen=True, slots=True)
class PolicyCatalog:
    """Из чего собирается документ политики — для редактора."""

    builtin: str
    legacy_scale: tuple[Grade, ...]  # шкала scorecard_v1 (A–E)
    pd_scale: tuple[Grade, ...]  # шкала PD-модели (A–J); по ней же зоны двух моделей
    outcomes: tuple[CodeName, ...]
    reasons: tuple[ReasonInfo, ...]  # коды причин, у которых есть текст
    stop_factors: tuple[str, ...]  # ключи раздела `stop_factors`
    registry_statuses: tuple[str, ...]  # статусы ЕГРЮЛ для `stop_factors.registry_statuses`
    routing_flags: tuple[str, ...]  # флаги для `routing.flags`
    zones: tuple[str, ...]  # зоны `strategy.two_models`
    zone_verdicts: tuple[str, ...]  # клетки матрицы двух моделей
    zsk_levels: tuple[str, ...]  # уровни ЗСК для `compliance.aml`
    legal_forms: tuple[str, ...]  # формы для `compliance.automated_decision_consent`
    collateral_types: tuple[CodeName, ...]  # ключи `limits.ltv`
    products: tuple[CodeName, ...]  # продукты, которые можно назвать альтернативой


class PolicyDocuments(Protocol):
    """Документ политики (тот же, что YAML): встроенная политика, проверка и сборка. Документ не
    прошёл проверку — `ValidationError` (422) со списком `{path, message}`."""

    @property
    def builtin_version(self) -> str: ...

    def builtin_body(self) -> dict[str, Any]: ...

    def builtin_policy(self) -> CreditPolicy: ...

    def normalize(self, body: Mapping[str, Any], version: str) -> dict[str, Any]: ...

    def compile(self, body: Mapping[str, Any], version: str) -> CreditPolicy: ...

    def catalog(self) -> PolicyCatalog: ...


@dataclass(frozen=True, slots=True)
class Verdict:
    outcome: Outcome
    reason_codes: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class PreviewItem:
    application_id: UUID
    result_id: UUID
    decided_at: datetime
    before: Verdict  # сохранённое автоматическое решение — своей версией политики
    after: Verdict  # как решила бы версия-кандидат на текущих данных


@dataclass(frozen=True, slots=True)
class OutcomeShift:
    from_outcome: Outcome
    to_outcome: Outcome
    count: int


@dataclass(frozen=True, slots=True)
class Preview:
    version: str
    items: tuple[PreviewItem, ...]
    transitions: tuple[OutcomeShift, ...]  # матрица переходов исходов, только непустые клетки
    changed: int  # другой исход или другие коды причин
    outcome_changed: int  # другой исход
    skipped: int  # вход не собрать (заявки или продукта уже нет) — пропущена


class PolicyProvider(Protocol):
    """Какой политикой решать сейчас."""

    async def active(self, versions: PolicyVersionRepository) -> CreditPolicy: ...


class FixedPolicy:
    """Всегда одна и та же политика, БД не спрашивает: тесты и golden."""

    def __init__(self, policy: CreditPolicy) -> None:
        self._policy = policy

    async def active(self, versions: PolicyVersionRepository) -> CreditPolicy:
        return self._policy


class ActivePolicyProvider:
    """Активная версия админа или, если её нет, встроенная политика."""

    def __init__(self, documents: PolicyDocuments) -> None:
        self._documents = documents
        self._compiled: dict[str, CreditPolicy] = {}

    async def active(self, versions: PolicyVersionRepository) -> CreditPolicy:
        code = await versions.active_version()
        if code is None:
            return self._documents.builtin_policy()
        policy = self._compiled.get(code)
        if policy is None:
            version = await versions.get(code)
            if version is None:  # активную версию не удалить — сюда не попасть
                raise RuntimeError(f"active policy version {code!r} is gone")
            policy = self._documents.compile(version.body, version.version)
            self._compiled[code] = policy
        return policy


class PolicyVersions:
    """Реестр версий кредитной политики для админки."""

    def __init__(
        self, repository: PolicyVersionRepository, documents: PolicyDocuments, clock: Clock
    ) -> None:
        self._repository = repository
        self._documents = documents
        self._clock = clock

    def catalog(self) -> PolicyCatalog:
        return self._documents.catalog()

    async def list_all(self) -> list[PolicyVersion]:
        """Встроенная первой, затем версии админа в порядке создания."""
        stored = await self._repository.list_all()
        overridden = any(v.status == "active" for v in stored)
        return [self._builtin(overridden=overridden), *stored]

    async def get(self, version: str) -> PolicyVersion:
        if version == self._documents.builtin_version:
            return self._builtin(overridden=await self._repository.active_version() is not None)
        found = await self._repository.get(version)
        if found is None:
            raise NotFoundError("Policy version not found", details={"version": version})
        return found

    async def create_draft(self, based_on: str, comment: str | None, by: UUID) -> PolicyVersion:
        """Черновик — копия любой версии под следующим номером `<встроенная>.<n>`."""
        source = await self.get(based_on)
        code = next_version(base_of(source.version), await self._repository.codes())
        draft = PolicyVersion.draft(
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
    ) -> PolicyVersion:
        draft = await self.get(version)
        draft.ensure_draft("update")
        draft.edit(self._body(body, draft.version), comment, self._clock.now())
        await self._repository.save(draft)
        return draft

    async def delete_draft(self, version: str) -> None:
        draft = await self.get(version)
        draft.ensure_draft("delete")
        await self._repository.delete(draft.version)

    async def activate(self, version: str, by: UUID) -> PolicyVersion:
        """Черновик или архивная версия становится активной, прежняя активная — архивной.
        Встроенная политика «активируется» тем, что активная версия из БД уходит в архив."""
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

    async def preview(
        self,
        version: str,
        limit: int,
        history: DecisionHistory,
        inputs: InputBuilders,
        key_rate: Decimal,
    ) -> Preview:
        """Последние заявки с автоматическим решением — версией-кандидатом, без записи. Как в
        процессе: сначала стоп-факторы (CheckStopFactors), не сработали — решение
        (MakeDecision)."""
        candidate = await self.get(version)
        policy = (
            self._documents.builtin_policy()
            if candidate.builtin
            else self._documents.compile(candidate.body, candidate.version)
        )
        builder = inputs(policy)
        items: list[PreviewItem] = []
        skipped = 0
        for result in await history.recent_automatic(limit):
            try:
                collected = await builder.collect(result.application_id)
            except (AppError, LookupError, TypeError, ValueError, ArithmeticError):
                logger.warning(
                    "Policy preview skips application %s", result.application_id, exc_info=True
                )
                skipped += 1
                continue
            decision_input = collected.decision_input
            decision = policy.screen(decision_input, key_rate=key_rate) or policy.decide(
                decision_input, key_rate=key_rate
            )
            items.append(
                PreviewItem(
                    application_id=result.application_id,
                    result_id=result.id,
                    decided_at=result.decided_at,
                    before=Verdict(result.outcome, result.reason_codes, result.policy_version),
                    after=Verdict(
                        decision.outcome,
                        tuple(str(code) for code in decision.reason_codes),
                        decision.policy_version,
                    ),
                )
            )
        return _summary(candidate.version, items, skipped)

    async def _current(self) -> PolicyVersion | None:
        code = await self._repository.active_version()
        return None if code is None else await self._repository.get(code)

    def _builtin(self, *, overridden: bool) -> PolicyVersion:
        return PolicyVersion(
            version=self._documents.builtin_version,
            status="archived" if overridden else "active",
            body=self._documents.builtin_body(),
            builtin=True,
        )

    def _body(self, body: Mapping[str, Any], version: str) -> dict[str, Any]:
        """Код версии внутри документа — всегда код самой версии: он пишется в решения."""
        return self._documents.normalize({**body, "version": version}, version)


def _summary(version: str, items: list[PreviewItem], skipped: int) -> Preview:
    shifts = Counter((item.before.outcome, item.after.outcome) for item in items)
    return Preview(
        version=version,
        items=tuple(items),
        transitions=tuple(
            OutcomeShift(before, after, count)
            for (before, after), count in sorted(
                shifts.items(),
                key=lambda shift: (
                    OUTCOME_ORDER.index(shift[0][0]),
                    OUTCOME_ORDER.index(shift[0][1]),
                ),
            )
        ),
        changed=sum(
            1
            for item in items
            if (item.before.outcome, item.before.reason_codes)
            != (item.after.outcome, item.after.reason_codes)
        ),
        outcome_changed=sum(1 for item in items if item.before.outcome != item.after.outcome),
        skipped=skipped,
    )
