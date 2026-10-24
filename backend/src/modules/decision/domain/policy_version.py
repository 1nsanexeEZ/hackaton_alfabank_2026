"""Версии кредитной политики, которые ведёт админ: черновик → активная → архив.

Встроенная политика (`policy_v10.yaml`) в БД не лежит: она только читается и действует, пока ни
одна версия админа не активна. Код версии админа — `<встроенная>.<n>` (`policy_v10.1`): так он
не пересечётся с будущими YAML-версиями разработчиков и влезет в `String(32)`.

Править и удалять можно только черновик: по активной и архивной версиям уже приняты решения,
они неизменны. Активировать можно черновик или архивную версию — второе и есть откат.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from src.core.exceptions.exceptions import InvalidStatusTransitionError
from src.modules.decision.domain.model import Outcome

PolicyStatus = Literal["draft", "active", "archived"]
# Исходы от лучшего для клиента к худшему: в этом порядке примерка строит матрицу переходов.
OUTCOME_ORDER: tuple[Outcome, ...] = (
    "APPROVE",
    "COUNTER_OFFER",
    "REQUEST_INFO",
    "MANUAL_REVIEW",
    "REJECT",
)


@dataclass(slots=True)
class PolicyVersion:
    version: str
    status: PolicyStatus
    body: dict[str, Any]  # тот же документ, что YAML: Decimal строками
    based_on: str | None = None
    comment: str | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    activated_by: UUID | None = None
    activated_at: datetime | None = None
    builtin: bool = False  # из YAML: только читается

    @classmethod
    def draft(
        cls,
        version: str,
        body: dict[str, Any],
        *,
        based_on: str,
        comment: str | None,
        by: UUID,
        now: datetime,
    ) -> PolicyVersion:
        return cls(
            version=version,
            status="draft",
            body=body,
            based_on=based_on,
            comment=comment,
            created_by=by,
            created_at=now,
            updated_at=now,
        )

    def edit(self, body: dict[str, Any], comment: str | None, now: datetime) -> None:
        self.ensure_draft("update")
        self.body = body
        if comment is not None:
            self.comment = comment
        self.updated_at = now

    def ensure_draft(self, action: str) -> None:
        if self.status != "draft":
            raise InvalidStatusTransitionError(
                "Only a draft can be changed",
                details={"version": self.version, "status": self.status, "action": action},
            )

    def activate(self, by: UUID, now: datetime) -> None:
        if self.status not in ("draft", "archived"):
            raise InvalidStatusTransitionError(
                details={"version": self.version, "from": self.status, "to": "active"}
            )
        self.status = "active"
        self.activated_by = by
        self.activated_at = now
        self.updated_at = now

    def archive(self, now: datetime) -> None:
        if self.status != "active":
            raise InvalidStatusTransitionError(
                details={"version": self.version, "from": self.status, "to": "archived"}
            )
        self.status = "archived"
        self.updated_at = now


def base_of(version: str) -> str:
    """`policy_v10.3` → `policy_v10`: от какой встроенной политики идёт версия."""
    return version.partition(".")[0]


def next_version(base: str, taken: Iterable[str]) -> str:
    """Следующий свободный номер версии админа: `policy_v10.1`, `policy_v10.2`…"""
    numbers = [
        int(number)
        for code in taken
        for prefix, _, number in [code.partition(".")]
        if prefix == base and number.isdigit()
    ]
    return f"{base}.{max(numbers, default=0) + 1}"
