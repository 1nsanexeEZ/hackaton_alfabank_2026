"""Предскрин учредителя стартапа: личная кредитная история вместо оборотов, которых ещё нет.

Ветка «нет бизнеса» общей схемы: «личный скоринг учредителя (предскрин) → прошёл?». Проверяем
текущую просрочку, серьёзную просрочку за 12 месяцев, число недавних запросов и платежи по
кредитам. Истории нет — проверять нечего, предскрин пройден: молодой предприниматель без
кредитов не хуже того, кто их гасит.

Пороги — в YAML (`PrescreenConfig`), логика — здесь; `check` — чистая функция входа. Тексты
причин видит клиент: без цифр порогов, по-человечески.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PersonHistoryInput:
    current_overdue_days: int  # наибольшая текущая просрочка по действующим кредитам
    max_overdue_days_12m: int
    inquiries_last_30d: int
    monthly_payments: Decimal
    obligations: int


@dataclass(frozen=True, slots=True)
class PrescreenConfig:
    version: str
    current_overdue_days: int  # текущая просрочка от стольких дней — не прошёл
    max_overdue_days_12m: int  # просрочка за 12 месяцев строго больше — не прошёл
    inquiries_30d: int  # запросов за 30 дней строго больше — не прошёл
    monthly_payments: Decimal  # платежи по кредитам в месяц строго больше — не прошёл


@dataclass(frozen=True, slots=True)
class PrescreenReason:
    code: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class PrescreenOutput:
    version: str
    passed: bool
    reasons: tuple[PrescreenReason, ...]


class FounderPrescreen:
    def __init__(self, config: PrescreenConfig) -> None:
        self._c = config

    @property
    def version(self) -> str:
        return self._c.version

    def check(self, history: PersonHistoryInput | None) -> PrescreenOutput:
        if history is None or (history.obligations == 0 and history.max_overdue_days_12m == 0):
            reasons: tuple[PrescreenReason, ...] = (
                PrescreenReason(
                    "no_history", True, "Личных кредитов нет — по кредитной истории замечаний нет"
                ),
            )
            if history is not None:
                reasons += (self._inquiries(history),)
            return self._output(reasons)
        return self._output(
            (
                self._current_overdue(history),
                self._past_overdue(history),
                self._inquiries(history),
                self._payments(history),
            )
        )

    def _current_overdue(self, history: PersonHistoryInput) -> PrescreenReason:
        if history.current_overdue_days >= self._c.current_overdue_days:
            return PrescreenReason(
                "no_current_overdue", False, "Есть текущая просрочка по личным кредитам"
            )
        return PrescreenReason(
            "no_current_overdue", True, "Текущей просрочки по личным кредитам нет"
        )

    def _past_overdue(self, history: PersonHistoryInput) -> PrescreenReason:
        if history.max_overdue_days_12m > self._c.max_overdue_days_12m:
            return PrescreenReason(
                "no_serious_overdue",
                False,
                "За последний год была длительная просрочка по личным кредитам",
            )
        return PrescreenReason(
            "no_serious_overdue", True, "Длительных просрочек за последний год не было"
        )

    def _inquiries(self, history: PersonHistoryInput) -> PrescreenReason:
        if history.inquiries_last_30d > self._c.inquiries_30d:
            return PrescreenReason(
                "few_inquiries", False, "Много обращений за кредитами за последний месяц"
            )
        return PrescreenReason(
            "few_inquiries", True, "Обращений за кредитами в последний месяц немного"
        )

    def _payments(self, history: PersonHistoryInput) -> PrescreenReason:
        if history.monthly_payments > self._c.monthly_payments:
            return PrescreenReason(
                "debt_load", False, "Высокие ежемесячные платежи по личным кредитам"
            )
        return PrescreenReason("debt_load", True, "Платежи по личным кредитам посильные")

    def _output(self, reasons: tuple[PrescreenReason, ...]) -> PrescreenOutput:
        return PrescreenOutput(
            version=self._c.version,
            passed=all(r.passed for r in reasons),
            reasons=reasons,
        )
