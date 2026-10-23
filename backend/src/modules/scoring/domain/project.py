"""Проектная оценка стартапа: бизнес-план и финмодель вместо оборотов и отчётности.

Ветка «нет бизнеса» общей схемы: предскрин учредителя → бизнес-план и финмодель → проектная
оценка → «вам предодобрен кредит». Правила по порядку, все проверяются, клиент видит каждое:
1. предскрин учредителя пройден и действует;
2. отрасль проекта не из списка повышенного риска для кредита на запуск;
3. DSCR по финмодели: денежный поток за горизонт модели (выручка − расходы по месяцам) к
   платежам по кредиту за тот же горизонт — не ниже порога;
4. собственные средства — не меньше доли в финансировании проекта (свои + кредит);
5. покрытие: залог с дисконтом и гарантия господдержки (не выше потолка доли) к сумме кредита —
   не ниже порога.

Правила 3–5 считаются на запрошенной сумме. Максимальная сумма — наибольшая, при которой
проходят все три (минимум из трёх ограничений); не прошли 1–2 или денежного потока нет —
кредит не выдержит никакой суммы, максимум 0. Рамки продукта, шаг суммы и само предложение —
дело decision.

Пороги — в YAML (`ProjectConfig`), логика — здесь; `assess` — чистая функция входа. Тексты
причин видит клиент: без цифр порогов, по-человечески.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from src.core.domain.annuity import annuity_payment, max_principal
from src.modules.scoring.domain.scorecard import okved_section

_ZERO = Decimal(0)
_ONE = Decimal(1)
_KOPECK = Decimal("0.01")
_SHARE = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class ProjectInput:
    monthly_revenue: tuple[Decimal, ...]  # по месяцам от первого месяца проекта
    monthly_expenses: tuple[Decimal, ...]  # операционные, без платежей по этому кредиту
    own_funds: Decimal
    collateral_value: Decimal  # рыночная стоимость залога, 0 — залога нет
    guarantee_share: Decimal  # доля кредита под гарантией господдержки, 0 — гарантии нет
    amount: Decimal  # запрошенная сумма
    term_months: int
    rate: Decimal  # % годовых для платежа
    okved_main: str
    prescreen_passed: bool


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    version: str
    horizon_months: int  # горизонт финмодели
    min_dscr: Decimal
    min_own_share: Decimal  # доля своих средств в финансировании проекта
    collateral_discount: Decimal  # залог берём по такой доле стоимости
    max_guarantee_share: Decimal  # гарантию господдержки учитываем не выше такой доли кредита
    min_coverage: Decimal  # (залог с дисконтом + гарантия) / сумма
    industry_high: frozenset[int]  # секции ОКВЭД, где кредит на запуск не выдаём


@dataclass(frozen=True, slots=True)
class ProjectReason:
    code: str  # founder_prescreen | industry | dscr | own_funds | coverage
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class ProjectMetrics:
    """Цифры для андеррайтера на запрошенной сумме; клиенту — не показываем."""

    cash_flow: Decimal  # выручка − расходы за горизонт
    debt_service: Decimal  # платежи по кредиту за горизонт
    dscr: Decimal | None  # None — платежей нет
    own_share: Decimal
    coverage: Decimal


@dataclass(frozen=True, slots=True)
class ProjectOutput:
    version: str
    passed: bool
    reasons: tuple[ProjectReason, ...]
    max_amount: Decimal
    metrics: ProjectMetrics


class ProjectAssessment:
    def __init__(self, config: ProjectConfig) -> None:
        self._c = config

    @property
    def version(self) -> str:
        return self._c.version

    def assess(self, project: ProjectInput) -> ProjectOutput:
        horizon = self._c.horizon_months
        if len(project.monthly_revenue) < horizon or len(project.monthly_expenses) < horizon:
            raise ValueError(f"В финмодели нужно {horizon} месяцев выручки и расходов")
        if project.amount <= 0 or project.term_months <= 0:
            raise ValueError("Нужны сумма и срок кредита")
        cash_flow = sum(
            (
                revenue - expenses
                for revenue, expenses in zip(
                    project.monthly_revenue[:horizon],
                    project.monthly_expenses[:horizon],
                    strict=True,
                )
            ),
            _ZERO,
        )
        paid_months = min(project.term_months, horizon)
        payment = annuity_payment(project.amount, project.term_months, project.rate)
        debt_service = payment * paid_months
        dscr = cash_flow / debt_service if debt_service > 0 else None
        own_share = project.own_funds / (project.own_funds + project.amount)
        guarantee = min(project.guarantee_share, self._c.max_guarantee_share)
        coverage = (
            project.collateral_value * self._c.collateral_discount + guarantee * project.amount
        ) / project.amount

        reasons = (
            self._prescreen(project.prescreen_passed),
            self._industry(project.okved_main),
            self._dscr(dscr),
            self._own_funds(own_share),
            self._coverage(coverage),
        )
        blocked = not reasons[0].passed or not reasons[1].passed or cash_flow <= 0
        max_amount = (
            _ZERO if blocked else self._max_amount(project, cash_flow, paid_months, guarantee)
        )
        return ProjectOutput(
            version=self._c.version,
            passed=all(r.passed for r in reasons),
            reasons=reasons,
            max_amount=max_amount,
            metrics=ProjectMetrics(
                cash_flow=cash_flow.quantize(_KOPECK),
                debt_service=debt_service.quantize(_KOPECK),
                dscr=dscr.quantize(_KOPECK, rounding=ROUND_DOWN) if dscr is not None else None,
                own_share=own_share.quantize(_SHARE, rounding=ROUND_DOWN),
                coverage=coverage.quantize(_SHARE, rounding=ROUND_DOWN),
            ),
        )

    def _max_amount(
        self, project: ProjectInput, cash_flow: Decimal, paid_months: int, guarantee: Decimal
    ) -> Decimal:
        """Наибольшая сумма, при которой проходят DSCR, свои средства и покрытие."""
        by_dscr = max_principal(
            (cash_flow / (self._c.min_dscr * paid_months)).quantize(_KOPECK, rounding=ROUND_DOWN),
            project.term_months,
            project.rate,
        )
        share = self._c.min_own_share
        by_own = project.own_funds * (_ONE - share) / share if share > 0 else by_dscr
        limits = [by_dscr, by_own]
        if guarantee < self._c.min_coverage:
            limits.append(
                project.collateral_value
                * self._c.collateral_discount
                / (self._c.min_coverage - guarantee)
            )
        return max(min(limits), _ZERO).quantize(_KOPECK, rounding=ROUND_DOWN)

    def _prescreen(self, passed: bool) -> ProjectReason:
        if passed:
            return ProjectReason("founder_prescreen", True, "Проверка учредителя пройдена")
        return ProjectReason(
            "founder_prescreen",
            False,
            "Нет действующей пройденной проверки учредителя — пройдите её в кабинете",
        )

    def _industry(self, okved_main: str) -> ProjectReason:
        if okved_section(okved_main) in self._c.industry_high:
            return ProjectReason(
                "industry", False, "В этой отрасли кредит на запуск бизнеса не выдаём"
            )
        return ProjectReason("industry", True, "Отрасль проекта подходит для кредита на запуск")

    def _dscr(self, dscr: Decimal | None) -> ProjectReason:
        if dscr is None or dscr < self._c.min_dscr:
            return ProjectReason(
                "dscr",
                False,
                "Денежного потока по финмодели не хватает на платежи по кредиту с запасом",
            )
        return ProjectReason(
            "dscr", True, "Денежного потока по финмодели хватает на платежи по кредиту с запасом"
        )

    def _own_funds(self, own_share: Decimal) -> ProjectReason:
        if own_share < self._c.min_own_share:
            return ProjectReason(
                "own_funds", False, "Собственных средств в проекте мало для такой суммы кредита"
            )
        return ProjectReason("own_funds", True, "Собственных средств в проекте достаточно")

    def _coverage(self, coverage: Decimal) -> ProjectReason:
        if coverage < self._c.min_coverage:
            return ProjectReason(
                "coverage",
                False,
                "Кредит недостаточно покрыт залогом или гарантией господдержки",
            )
        return ProjectReason("coverage", True, "Кредит покрыт залогом или гарантией господдержки")
