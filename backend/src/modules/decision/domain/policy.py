"""CreditPolicy — правила банка: что предложить этому заёмщику по этому продукту.

Правила идут по порядку, первое терминальное останавливает конвейер, всё проверенное пишется в
`rule_trace` (сработало правило или нет и почему):

1. стоп-факторы → REJECT без вариантов: ликвидация/банкротство по ЕГРЮЛ, дисквалификация
   руководителя, просрочка > 90 дней, грейд E; с policy_v2 ещё — текущая просрочка компании
   или руководителя, блокировки счетов и недоимка выше порога (ФНС), сообщения о банкротстве,
   исполнительные производства и иски выше доли выручки (Контур), отрицательный капитал
   (ГИР БО), массовый адрес и ОКВЭД из стоп-листа;
2. дозапрос → REQUEST_INFO: флаг `revenue_mismatch`, а закрытого дозапроса выписки ещё не было;
3. ставка: база продукта + надбавка за грейд − скидка за залог + (ключевая − опорная),
   в коридоре продукта; господдержка — не выше потолка программы;
4. лимит: min(продукт, k(грейд) × выручка, LTV × залог, платёжеспособность);
5. маршрутизация → MANUAL_REVIEW: сумма выше лимита автоматики, грейд D, расхождения, сбой
   источников, массовый адрес, с policy_v2 — недоимка по налогам (`thin_file` не маршрутизирует);
6. исход: APPROVE как просили / COUNTER_OFFER (лимит вниз до 10 000, срок подобран в рамках
   продукта) / REJECT с альтернативным продуктом.

Кассовый разрыв по выписке не меняет исход, но даёт условие в оффере, альтернативу
(овердрафт или кредитная линия — что проходит eligibility) и объяснение клиенту.

policy_v3 — «Стратегия решения» общей схемы на грейдах A–J PD-модели:
- мягкие триггеры (недоимка, смена руководителя, «разгон» оборотов по выписке) → ручная
  проверка, они в `triggers`; вместе со сбоем источников идут раньше матрицы;
- матрица грейд × сумма по корзинам грейдов → одобрить (дальше лимиты) / ручная / отказ;
- лимит — минимум из ограничений: продукт, выручка, обороты по счёту, платёжеспособность,
  грейд, кредиты группы, для залоговых — LTV; `binding` — какое дало минимум;
- ставка = фондирование (ключевая + спред) + EL (PD × LGD) + капитал + маржа, в коридоре
  продукта, разбивка — в `rate_breakdown`;
- поручительство собственника — для слабых грейдов и крупных сумм.

Порог и коэффициенты — в `PolicyConfig` (YAML в инфраструктуре); `decide` — чистая функция
входа и ключевой ставки, без IO и без `now()`. Правила policy_v2 и policy_v3 включаются своими
ключами в YAML: нет ключа — нет правила и нет строки в трассе, поэтому решения прежних версий
не меняются.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Literal

from src.modules.decision.domain.explanations import ExplanationCatalog, month_in, render, rub
from src.modules.decision.domain.model import (
    LEGACY_SCALE,
    AlternativeInput,
    CompanyInput,
    DecisionInput,
    Grade,
    InfoNeed,
    Limits,
    OfferTerms,
    Outcome,
    PolicyDecision,
    PreApproval,
    PreApprovalInput,
    ProductInput,
    RateBreakdown,
    ReasonCode,
    RuleHit,
    ScoreInput,
    Trigger,
)

_ZERO = Decimal(0)
_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)
_MONTHLY_DIVISOR = Decimal(1200)  # 12 месяцев × 100 %
_TWELVE = Decimal(12)
_MAX_HINTS = 4
_HEAD_BUREAU_SKIPPED = {
    "no_consent": "нет согласия руководителя на запрос его БКИ — проверка не выполнена",
    "no_head": "руководитель по реестру не найден среди участников — проверка не выполнена",
    "failed": "БКИ руководителя не ответило — проверка не выполнена",
    "not_requested": "БКИ руководителя не запрашивалось — проверка не выполнена",
}


MatrixVerdict = Literal["approve", "manual", "reject"]


@dataclass(frozen=True, slots=True)
class MatrixBand:
    """Корзина грейдов матрицы policy_v3: до какой суммы решает автоматика, до какой — человек;
    выше — отказ. `manual_up_to` None — без верхней границы."""

    label: str  # «A–C»
    grades: frozenset[str]
    approve_up_to: Decimal
    manual_up_to: Decimal | None

    def verdict(self, amount: Decimal) -> MatrixVerdict:
        if amount <= self.approve_up_to:
            return "approve"
        if self.manual_up_to is None or amount <= self.manual_up_to:
            return "manual"
        return "reject"


@dataclass(frozen=True, slots=True)
class RateComponents:
    """Ставка policy_v3 из компонент, проценты годовых; LGD и PD — доли."""

    funding_spread: Decimal  # фондирование = ключевая + спред
    lgd_unsecured: Decimal
    lgd_secured: Decimal  # залог покрывает сумму не меньше collateral_min_coverage
    capital: Decimal
    margin: Decimal
    pd_if_unknown: Decimal  # у результата scorecard_v1 PD нет — берём осторожную


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    version: str
    key_rate_reference: Decimal
    stop_registry_statuses: Mapping[str, ReasonCode]
    stop_overdue_days: int  # просрочка строго больше — стоп
    stop_grades: frozenset[str]
    revenue_document: str
    revenue_multiplier: Mapping[str, Decimal]  # грейд → k
    ltv: Mapping[str, Decimal]  # тип залога → LTV
    payment_share: Decimal  # доля свободного потока на платёж
    assumed_expense_ratio: Decimal  # нет расходов в отчёте → доля выручки
    amount_step: Decimal
    grade_premium: Mapping[str, Decimal]
    collateral_discount: Decimal
    collateral_min_coverage: Decimal
    manual_review_grades: frozenset[str]
    routing_flags: Mapping[str, ReasonCode]
    cash_gap_products: tuple[str, ...]
    secured_product: str
    small_amount_product: str
    offer_valid_days: int
    # policy_v2. None / False / пусто — правило выключено (так ведёт себя policy_v1).
    stop_current_overdue_days: int | None = None  # текущая просрочка компании и руководителя
    stop_account_blocks: bool = False
    stop_tax_arrears_above: Decimal | None = None  # недоимка строго больше — стоп
    stop_bankruptcy_messages: bool = False
    stop_enforcement_share: Decimal | None = None  # исп. производства > доли годовой выручки
    stop_lawsuits_share: Decimal | None = None  # иски к компании > доли годовой выручки
    stop_negative_equity: bool = False
    stop_mass_address: bool = False
    stop_okved_classes: frozenset[str] = frozenset()  # двузначные классы ОКВЭД
    route_tax_arrears: bool = False  # недоимка > 0 (не выше стоп-порога) → ручная проверка
    # policy_v3. Пусто / None — правило выключено (так ведут себя policy_v1 и policy_v2).
    grade_scale: tuple[Grade, ...] = LEGACY_SCALE
    risk_matrix: tuple[MatrixBand, ...] = ()
    trigger_tax_arrears: bool = False
    trigger_head_change_months: int | None = None  # руководитель сменился меньше N мес. назад
    trigger_turnover_months: int | None = None  # последние N месяцев выписки…
    trigger_turnover_ratio: Decimal | None = None  # …к среднему за прежние больше — «разгон»
    turnover_multiplier: Decimal | None = None  # лимит ≤ k × обороты по счёту за год
    grade_max_amount: Mapping[str, Decimal] = field(default_factory=dict)
    group_exposure_max: Decimal | None = None  # лимит ≤ потолок − долг по действующим кредитам
    rate_components: RateComponents | None = None
    guarantee_grades: frozenset[str] = frozenset()
    guarantee_amount_above: Decimal | None = None
    # policy_v4: продукты для стартапа — нужен пройденный предскрин учредителя, вместо матрицы
    # грейд × сумма — проектная оценка андеррайтером.
    startup_products: frozenset[str] = frozenset()

    def band(self, grade: str) -> MatrixBand | None:
        return next((b for b in self.risk_matrix if grade in b.grades), None)

    @property
    def full_limits(self) -> bool:
        """policy_v3: лимит — минимум из всех ограничений, с тем, какое сработало."""
        return (
            bool(self.grade_max_amount)
            or self.group_exposure_max is not None
            or self.turnover_multiplier is not None
        )


class CreditPolicy:
    def __init__(self, config: PolicyConfig, explanations: ExplanationCatalog) -> None:
        self._c = config
        self._x = explanations

    @property
    def version(self) -> str:
        return self._c.version

    @property
    def config(self) -> PolicyConfig:
        return self._c

    def alternative_candidates(self, product_code: str) -> tuple[str, ...]:
        """Продукты, eligibility которых нужна для альтернативы (без запрошенного)."""
        codes = (*self._c.cash_gap_products, self._c.secured_product, self._c.small_amount_product)
        return tuple(code for code in dict.fromkeys(codes) if code != product_code)

    def decide(self, inp: DecisionInput, *, key_rate: Decimal) -> PolicyDecision:
        return _Evaluation(self._c, self._x, inp, key_rate).run()

    def pre_approve(self, inp: PreApprovalInput, *, key_rate: Decimal) -> PreApproval | None:
        """Предодобренное предложение по продукту; None — предложить нечего (стоп-фактор,
        выручка неизвестна или лимит ниже минимума продукта). Eligibility проверяет вызывающий."""
        return _pre_approve(self._c, inp, key_rate)


# --- расчётные функции (общие для решения и предодобрения) -----------------------------------


def annuity_payment(amount: Decimal, term_months: int, rate: Decimal) -> Decimal:
    """Аннуитетный платёж, округлён до копеек — та же формула, что в products."""
    monthly = rate / _MONTHLY_DIVISOR
    if monthly == 0:
        return (amount / term_months).quantize(_CENT, rounding=ROUND_HALF_UP)
    payment = amount * monthly / (1 - (1 + monthly) ** -term_months)
    return payment.quantize(_CENT, rounding=ROUND_HALF_UP)


def max_principal(payment: Decimal, term_months: int, rate: Decimal) -> Decimal:
    """Обратный аннуитет: наибольшая сумма, при которой платёж не превышает `payment`."""
    if payment <= 0:
        return _ZERO
    monthly = rate / _MONTHLY_DIVISOR
    if monthly == 0:
        principal = payment * term_months
    else:
        principal = payment * (1 - (1 + monthly) ** -term_months) / monthly
    return principal.quantize(_CENT, rounding=ROUND_DOWN)


def round_down(amount: Decimal, step: Decimal) -> Decimal:
    if amount <= 0:
        return _ZERO
    return ((amount / step).to_integral_value(rounding=ROUND_DOWN) * step).quantize(_CENT)


def quote_rate(
    config: PolicyConfig,
    product: ProductInput,
    grade: Grade,
    *,
    key_rate: Decimal,
    coverage: Decimal | None,
    okved_main: str,
    in_msp_registry: bool | None,
    pd: Decimal | None = None,
) -> tuple[Decimal, list[RuleHit], RateBreakdown | None]:
    """Ставка по шагам, в коридоре продукта; господдержка — не выше потолка программы, если
    компания проходит. policy_v1/v2: база + надбавка за грейд − скидка за залог + сдвиг ключевой
    ставки; policy_v3: фондирование + EL (PD × LGD) + капитал + маржа, разбивка — третьим."""
    parts: RateBreakdown | None = None
    if config.rate_components is not None:
        raw, hits, parts = _component_rate(
            config, config.rate_components, key_rate=key_rate, coverage=coverage, pd=pd
        )
    else:
        raw, hits = _grade_rate(config, product, grade, key_rate=key_rate, coverage=coverage)
    rate = min(max(raw, product.rate_base), product.rate_max)
    hits.append(
        RuleHit(
            "pricing.corridor",
            rate != raw,
            f"{_pct(raw)} в коридоре продукта [{_pct(product.rate_base)}; "
            f"{_pct(product.rate_max)}] → {_pct(rate)}",
        )
    )
    program = product.support_program
    if program is not None:
        qualifies = _qualifies_for_program(product, okved_main, in_msp_registry)
        capped = min(rate, program.rate_cap) if qualifies else rate
        hits.append(
            RuleHit(
                "pricing.support_program",
                qualifies and capped != rate,
                f"программа {program.code}: "
                + (
                    f"компания проходит, потолок {_pct(program.rate_cap)} → {_pct(capped)}"
                    if qualifies
                    else "компания не проходит требования (реестр МСП или ОКВЭД)"
                ),
            )
        )
        rate = capped
    final = rate.quantize(_CENT, rounding=ROUND_HALF_UP)
    if parts is not None:
        parts = replace(parts, total=final)
    return final, hits, parts


def _grade_rate(
    config: PolicyConfig,
    product: ProductInput,
    grade: Grade,
    *,
    key_rate: Decimal,
    coverage: Decimal | None,
) -> tuple[Decimal, list[RuleHit]]:
    """policy_v1/v2: база продукта + надбавка за грейд − скидка за залог + сдвиг ключевой."""
    premium = config.grade_premium.get(grade, _ZERO)
    discount = (
        config.collateral_discount
        if coverage is not None and coverage >= config.collateral_min_coverage
        else _ZERO
    )
    market = key_rate - config.key_rate_reference
    hits = [
        RuleHit("pricing.base", True, f"базовая ставка {product.code}: {_pct(product.rate_base)}"),
        RuleHit("pricing.grade_premium", premium != 0, f"грейд {grade}: +{_pct(premium)}"),
        RuleHit(
            "pricing.collateral_discount",
            discount != 0,
            "залога нет"
            if coverage is None
            else f"покрытие залогом {coverage.quantize(_CENT)}: −{_pct(discount)}",
        ),
        RuleHit(
            "pricing.key_rate",
            market != 0,
            f"ключевая {_pct(key_rate)} − опорная {_pct(config.key_rate_reference)} "
            f"= {'+' if market >= 0 else ''}{_pct(market)}",
        ),
    ]
    return product.rate_base + premium - discount + market, hits


def _component_rate(
    config: PolicyConfig,
    parts: RateComponents,
    *,
    key_rate: Decimal,
    coverage: Decimal | None,
    pd: Decimal | None,
) -> tuple[Decimal, list[RuleHit], RateBreakdown]:
    """policy_v3: фондирование + ожидаемые потери + капитал + маржа."""
    secured = coverage is not None and coverage >= config.collateral_min_coverage
    lgd = parts.lgd_secured if secured else parts.lgd_unsecured
    known_pd = pd if pd is not None else parts.pd_if_unknown
    funding = key_rate + parts.funding_spread
    expected_loss = (known_pd * lgd * _HUNDRED).quantize(_CENT, rounding=ROUND_HALF_UP)
    raw = funding + expected_loss + parts.capital + parts.margin
    pd_note = f"PD {known_pd}" if pd is not None else f"PD неизвестна, берём {known_pd}"
    collateral = (
        "залога нет"
        if coverage is None
        else f"покрытие залогом {coverage.quantize(_CENT)}"
        + (" — LGD залогового" if secured else " — меньше порога, LGD беззалогового")
    )
    hits = [
        RuleHit(
            "pricing.funding",
            True,
            f"фондирование: ключевая {_pct(key_rate)} + спред {_pct(parts.funding_spread)} "
            f"= {_pct(funding)}",
        ),
        RuleHit(
            "pricing.expected_loss",
            True,
            f"ожидаемые потери: {pd_note} × LGD {lgd} = {_pct(expected_loss)} ({collateral})",
        ),
        RuleHit("pricing.capital", True, f"стоимость капитала {_pct(parts.capital)}"),
        RuleHit("pricing.margin", True, f"маржа {_pct(parts.margin)}"),
    ]
    breakdown = RateBreakdown(funding, expected_loss, parts.capital, parts.margin, raw)
    return raw, hits, breakdown


def _qualifies_for_program(
    product: ProductInput, okved_main: str, in_msp_registry: bool | None
) -> bool:
    program = product.support_program
    if program is None:
        return False
    if program.msp_registry_required and in_msp_registry is not True:
        return False
    return okved_main.split(".", 1)[0] in program.okved_whitelist


def _pre_approve(
    config: PolicyConfig, inp: PreApprovalInput, key_rate: Decimal
) -> PreApproval | None:
    """Предодобрение по облегчённым данным (без БКИ и выписок): лимит на грейд осторожнее.
    В policy_v3 лимит не выше и того, что по этому грейду одобряет автоматика (матрица и
    ограничение по грейду): клиенту не предлагают сумму, которую потом не дадут."""
    if inp.registry_status in config.stop_registry_statuses or inp.grade in config.stop_grades:
        return None
    scale = config.grade_scale
    if inp.grade not in scale:
        return None
    revenue = inp.annual_revenue
    position = scale.index(inp.grade) + 1
    if position >= len(scale):
        return None
    cautious = scale[position]
    k = config.revenue_multiplier.get(cautious)
    if revenue is None or revenue <= 0 or k is None or cautious in config.stop_grades:
        return None
    product = inp.product
    ceilings = [product.amount_max]
    band = config.band(cautious)
    if band is not None:
        ceilings.append(band.approve_up_to)
    if config.grade_max_amount:
        ceilings.append(config.grade_max_amount.get(cautious, _ZERO))
    ceiling = min(ceilings)
    limit = round_down(min(ceiling, k * revenue), config.amount_step)
    if limit < product.amount_min:
        return None
    rate, _, _ = quote_rate(
        config,
        product,
        inp.grade,
        key_rate=key_rate,
        coverage=None,
        okved_main=inp.okved_main,
        in_msp_registry=inp.in_msp_registry,
        pd=inp.pd_12m,
    )
    pd = f", PD {inp.pd_12m}" if inp.pd_12m is not None else ""
    return PreApproval(
        product_code=product.code,
        max_amount=limit,
        rate_from=rate,
        term_max_months=product.term_max_months,
        factors_summary=(
            f"оценка без кредитной истории: грейд {inp.grade} (скор {inp.score}{pd})",
            f"лимит на ступень осторожнее: k({cautious}) {k} × выручка {_num(revenue)}, "
            f"не больше {_num(ceiling)} → {_num(limit)}",
            f"ставка от {_pct(rate)}: база {_pct(product.rate_base)}, грейд {inp.grade}, "
            f"ключевая {_pct(key_rate)}",
        ),
    )


def _num(value: Decimal) -> str:
    """Число для трассы банка: разряды пробелом, копейки только если есть."""
    quantized = value.quantize(_CENT, rounding=ROUND_HALF_UP)
    whole = int(quantized)
    text = f"{whole:,}".replace(",", " ")
    cents = abs(quantized - whole)
    return f"{text},{int(cents * 100):02d}" if cents else text


def _pct(value: Decimal) -> str:
    return f"{value.quantize(_CENT, rounding=ROUND_HALF_UP)}%"


class _Evaluation:
    """Один прогон политики: копит трассу правил и собирает итог."""

    def __init__(
        self,
        config: PolicyConfig,
        explanations: ExplanationCatalog,
        inp: DecisionInput,
        key_rate: Decimal,
    ) -> None:
        self._c = config
        self._x = explanations
        self._in = inp
        self._key_rate = key_rate
        self._trace: list[RuleHit] = []
        self._limits = Limits()
        self._rate: Decimal | None = None
        self._rate_breakdown: RateBreakdown | None = None
        self._triggers: list[Trigger] = []

    def run(self) -> PolicyDecision:
        score = self._in.score
        if score is None:
            self._hit("input.scoring", True, "результата скоринга нет — решение за андеррайтером")
            return self._result("MANUAL_REVIEW", (ReasonCode.ROUTE_SOURCES_FAILED,))

        stops = self._stop_factors(score)
        if stops:
            return self._result("REJECT", stops)

        info = self._info_request(score)
        if info is not None:
            return self._result(
                "REQUEST_INFO", (ReasonCode.INFO_REVENUE_NOT_CONFIRMED,), requested_info=info
            )

        self._rate = self._pricing(score)
        max_payment = self._limits_for(score.grade, self._rate)
        routes = list(self._routing(score))
        self._soft_triggers()
        verdict = self._risk_matrix(score.grade)
        gap, gap_alternative = self._cash_gap(score)
        if self._triggers:
            routes.append(ReasonCode.ROUTE_SOFT_TRIGGER)
        # Неполные данные и мягкие триггеры — раньше матрицы: решает человек, а не отказ.
        early = bool(self._triggers) or ReasonCode.ROUTE_SOURCES_FAILED in routes
        if verdict == "reject" and not early:
            return self._result("REJECT", (ReasonCode.STOP_RISK_MATRIX,))
        if verdict in ("manual", "reject"):
            routes.append(ReasonCode.ROUTE_RISK_MATRIX)
        if routes:
            return self._result("MANUAL_REVIEW", tuple(routes))
        return self._outcome(self._rate, max_payment, gap, gap_alternative)

    # --- 1. стоп-факторы ---------------------------------------------------------------------

    def _stop_factors(self, score: ScoreInput) -> tuple[ReasonCode, ...]:
        company, bureau = self._in.company, self._in.bureau
        reasons: list[ReasonCode] = []

        registry_stop = self._c.stop_registry_statuses.get(company.registry_status)
        self._hit(
            "stop.registry_status",
            registry_stop is not None,
            f"статус по ЕГРЮЛ: {company.registry_status}",
        )
        if registry_stop is not None:
            reasons.append(registry_stop)

        disqualified = company.disqualified_head is True
        self._hit(
            "stop.disqualified_head",
            disqualified,
            "руководитель дисквалифицирован (ФНС)"
            if disqualified
            else (
                "ФНС не ответила — проверка не выполнена"
                if company.disqualified_head is None
                else "руководитель не дисквалифицирован"
            ),
        )
        if disqualified:
            reasons.append(ReasonCode.STOP_DISQUALIFIED_HEAD)

        overdue = bureau.max_overdue_days
        overdue_stop = overdue is not None and overdue > self._c.stop_overdue_days
        self._hit(
            "stop.overdue",
            overdue_stop,
            "БКИ недоступно — проверка не выполнена"
            if overdue is None
            else f"максимальная просрочка {overdue} дн., порог > {self._c.stop_overdue_days}",
        )
        if overdue_stop:
            reasons.append(ReasonCode.STOP_OVERDUE_90)

        self._external_stops(reasons)
        prescreen = self._founder_prescreen()
        if prescreen is not None:
            reasons.append(prescreen)

        # В policy_v3 грейд отсекает матрица, а не стоп-фактор.
        if self._c.stop_grades:
            grade_stop = score.grade in self._c.stop_grades
            self._hit("stop.grade", grade_stop, f"грейд {score.grade} (скор {score.score})")
            if grade_stop:
                reasons.append(ReasonCode.STOP_GRADE_E)
        return tuple(reasons)

    def _external_stops(self, reasons: list[ReasonCode]) -> None:
        """Стоп-факторы policy_v2: каждое правило — только если оно включено в YAML."""
        company, counterparty = self._in.company, self._in.counterparty
        checks = (
            self._current_overdue(),
            self._head_overdue(),
            self._account_blocks(company),
            self._tax_arrears_stop(company),
            self._bankruptcy_messages(),
            self._revenue_share(
                "stop.enforcement",
                self._c.stop_enforcement_share,
                "исполнительные производства",
                counterparty.enforcement_sum if counterparty is not None else None,
                ReasonCode.STOP_LARGE_ENFORCEMENT,
            ),
            self._revenue_share(
                "stop.lawsuits",
                self._c.stop_lawsuits_share,
                "иски к компании",
                counterparty.lawsuits_sum if counterparty is not None else None,
                ReasonCode.STOP_LARGE_LAWSUITS,
            ),
            self._negative_equity(),
            self._mass_address(company),
            self._okved(company),
        )
        reasons.extend(code for code in checks if code is not None)

    def _founder_prescreen(self) -> ReasonCode | None:
        """policy_v4: заявка на продукт для стартапа — только с пройденным предскрином."""
        if self._in.product.code not in self._c.startup_products:
            return None
        status = self._in.founder_prescreen or "missing"
        details = {
            "passed": "предскрин учредителя пройден",
            "failed": "предскрин учредителя не пройден",
            "expired": "предскрин учредителя истёк к подаче заявки",
            "missing": "предскрина учредителя не было",
        }
        matched = status != "passed"
        self._hit("stop.founder_prescreen", matched, details[status])
        return ReasonCode.STOP_FOUNDER_PRESCREEN if matched else None

    def _current_overdue(self) -> ReasonCode | None:
        days = self._c.stop_current_overdue_days
        if days is None:
            return None
        current = self._in.bureau.current_overdue_days
        matched = current is not None and current >= days
        self._hit(
            "stop.current_overdue",
            matched,
            "БКИ недоступно — проверка не выполнена"
            if current is None
            else f"текущая просрочка компании {current} дн., порог ≥ {days}",
        )
        return ReasonCode.STOP_CURRENT_OVERDUE if matched else None

    def _head_overdue(self) -> ReasonCode | None:
        days = self._c.stop_current_overdue_days
        if days is None:
            return None
        head = self._in.head_bureau
        status = head.status if head is not None else "not_requested"
        current = (head.current_overdue_days if head is not None else None) or 0
        matched = status == "ok" and current >= days
        detail = (
            f"текущая просрочка руководителя {current} дн., порог ≥ {days}"
            if status == "ok"
            else _HEAD_BUREAU_SKIPPED[status]
        )
        self._hit("stop.head_overdue", matched, detail)
        return ReasonCode.STOP_HEAD_OVERDUE if matched else None

    def _account_blocks(self, company: CompanyInput) -> ReasonCode | None:
        if not self._c.stop_account_blocks:
            return None
        blocks = company.account_blocks
        matched = bool(blocks)
        self._hit(
            "stop.account_blocks",
            matched,
            "ФНС не ответила — проверка не выполнена"
            if blocks is None
            else f"решений о приостановлении операций по счетам: {blocks}",
        )
        return ReasonCode.STOP_ACCOUNT_BLOCKS if matched else None

    def _tax_arrears_stop(self, company: CompanyInput) -> ReasonCode | None:
        limit = self._c.stop_tax_arrears_above
        if limit is None:
            return None
        arrears = company.tax_arrears
        matched = arrears is not None and arrears > limit
        self._hit(
            "stop.tax_arrears",
            matched,
            "ФНС не ответила — проверка не выполнена"
            if arrears is None
            else f"недоимка {_num(arrears)}, порог > {_num(limit)}",
        )
        return ReasonCode.STOP_TAX_ARREARS if matched else None

    def _bankruptcy_messages(self) -> ReasonCode | None:
        if not self._c.stop_bankruptcy_messages:
            return None
        kontur = self._in.counterparty
        matched = kontur is not None and kontur.bankruptcy_messages > 0
        self._hit(
            "stop.bankruptcy_messages",
            matched,
            "Контур не ответил — проверка не выполнена"
            if kontur is None
            else f"сообщений о банкротстве: {kontur.bankruptcy_messages}",
        )
        return ReasonCode.STOP_BANKRUPTCY_MESSAGE if matched else None

    def _revenue_share(
        self,
        rule: str,
        share: Decimal | None,
        what: str,
        amount: Decimal | None,
        reason: ReasonCode,
    ) -> ReasonCode | None:
        """Сумма из Контура больше доли годовой выручки — стоп."""
        if share is None:
            return None
        if amount is None:
            self._hit(rule, False, "Контур не ответил — проверка не выполнена")
            return None
        revenue, basis = self._annual_revenue()
        if revenue is None:
            self._hit(rule, False, f"{what} {_num(amount)}; выручка неизвестна — не проверить")
            return None
        threshold = (share * revenue).quantize(_CENT, rounding=ROUND_DOWN)
        matched = amount > threshold
        self._hit(
            rule,
            matched,
            f"{what} {_num(amount)}, порог > {share} × выручка {_num(revenue)} ({basis}) "
            f"= {_num(threshold)}",
        )
        return reason if matched else None

    def _annual_revenue(self) -> tuple[Decimal | None, str]:
        """Годовая выручка для долевых порогов: ГИР БО, иначе ФНС, иначе отчёт клиента."""
        accounting, company = self._in.accounting, self._in.company
        if accounting is not None and accounting.revenue > 0:
            return accounting.revenue, f"ГИР БО за {accounting.year}"
        if company.reported_revenue:
            return company.reported_revenue, "ФНС"
        if company.declared_revenue:
            return company.declared_revenue, "отчёт клиента"
        return None, ""

    def _negative_equity(self) -> ReasonCode | None:
        if not self._c.stop_negative_equity:
            return None
        accounting = self._in.accounting
        matched = accounting is not None and accounting.equity < 0
        self._hit(
            "stop.negative_equity",
            matched,
            "отчётности в ГИР БО нет — проверка не выполнена"
            if accounting is None
            else f"собственный капитал за {accounting.year}: {_num(accounting.equity)}",
        )
        return ReasonCode.STOP_NEGATIVE_EQUITY if matched else None

    def _mass_address(self, company: CompanyInput) -> ReasonCode | None:
        if not self._c.stop_mass_address:
            return None
        matched = company.mass_address
        self._hit(
            "stop.mass_address",
            matched,
            "адрес массовой регистрации (ЕГРЮЛ)" if matched else "адрес не массовый",
        )
        return ReasonCode.STOP_MASS_ADDRESS if matched else None

    def _okved(self, company: CompanyInput) -> ReasonCode | None:
        if not self._c.stop_okved_classes:
            return None
        okved_class = company.okved_main.split(".", 1)[0]
        matched = okved_class in self._c.stop_okved_classes
        verdict = "в стоп-листе банка" if matched else "не в стоп-листе"
        self._hit("stop.okved", matched, f"основной ОКВЭД {company.okved_main} — {verdict}")
        return ReasonCode.STOP_FORBIDDEN_OKVED if matched else None

    # --- 2. дозапрос ---------------------------------------------------------------------------

    def _info_request(self, score: ScoreInput) -> InfoNeed | None:
        mismatch = "revenue_mismatch" in score.flags
        needed = mismatch and not self._in.revenue_info_requested
        if not mismatch:
            detail = "выручка не расходится с ФНС и выпиской"
        elif needed:
            detail = "выручка не подтверждена ФНС — запрашиваем выписку по счёту за 6 месяцев"
        else:
            detail = "выписку уже запрашивали — дальше решает маршрутизация"
        self._hit("info.revenue_confirmation", needed, detail)
        if not needed:
            return None
        return InfoNeed(
            fields=(),
            documents=(self._c.revenue_document,),
            comment=self._x.reasons[ReasonCode.INFO_REVENUE_NOT_CONFIRMED].text,
        )

    # --- 3. ставка -------------------------------------------------------------------------------

    def _pricing(self, score: ScoreInput) -> Decimal:
        collateral, amount = self._in.collateral, self._in.request.amount
        coverage = collateral.value / amount if collateral is not None and amount > 0 else None
        rate, hits, breakdown = quote_rate(
            self._c,
            self._in.product,
            score.grade,
            key_rate=self._key_rate,
            coverage=coverage,
            okved_main=self._in.company.okved_main,
            in_msp_registry=self._in.company.in_msp_registry,
            pd=score.pd_12m,
        )
        self._trace.extend(hits)
        self._rate_breakdown = breakdown
        return rate

    # --- 4. лимит --------------------------------------------------------------------------------

    def _limits_for(self, grade: Grade, rate: Decimal) -> Decimal:
        product, company, collateral = self._in.product, self._in.company, self._in.collateral
        request = self._in.request

        by_product = product.amount_max
        self._hit(
            "limits.product", by_product < request.amount, f"максимум продукта {_num(by_product)}"
        )

        revenues = [r for r in (company.declared_revenue, company.reported_revenue) if r]
        k = self._c.revenue_multiplier.get(grade, _ZERO)
        if revenues:
            basis = min(revenues)
            by_revenue = (k * basis).quantize(_CENT, rounding=ROUND_DOWN)
            self._hit(
                "limits.revenue",
                by_revenue < request.amount,
                f"k({grade}) {k} × выручка {_num(basis)} (меньшая из заявленной и ФНС) "
                f"= {_num(by_revenue)}",
            )
        else:
            by_revenue = _ZERO
            self._hit("limits.revenue", True, "выручка неизвестна — лимит от выручки 0")

        by_ltv: Decimal | None = None
        if product.collateral_required:
            if collateral is None:
                by_ltv = _ZERO
                self._hit("limits.ltv", True, "залог обязателен, но не указан — лимит 0")
            else:
                ltv = self._c.ltv.get(collateral.type, _ZERO)
                by_ltv = (ltv * collateral.value).quantize(_CENT, rounding=ROUND_DOWN)
                self._hit(
                    "limits.ltv",
                    by_ltv < request.amount,
                    f"LTV {collateral.type} {ltv} × залог {_num(collateral.value)} "
                    f"= {_num(by_ltv)}",
                )

        max_payment = self._max_payment()
        term = self._clamp_term(request.term_months)
        by_capacity = max_principal(max_payment, term, rate)
        self._hit(
            "limits.payment_capacity",
            by_capacity < request.amount,
            f"платёж ≤ {_num(max_payment)} в месяц: при {term} мес. и {_pct(rate)} "
            f"сумма до {_num(by_capacity)}",
        )

        by_turnover = self._turnover_limit()
        by_grade = self._grade_limit(grade)
        by_group = self._group_limit()

        candidates = {
            "by_product": by_product,
            "by_revenue": by_revenue,
            "by_turnover": by_turnover,
            "by_capacity": by_capacity,
            "by_grade": by_grade,
            "by_group": by_group,
            "by_ltv": by_ltv,
        }
        present = {name: value for name, value in candidates.items() if value is not None}
        final = min(present.values())
        binding = None
        if self._c.full_limits:
            binding = next(name for name, value in present.items() if value == final)
            self._hit("limits.final", True, f"лимит {_num(final)}: минимум — {binding}")
        self._limits = Limits(
            by_product=by_product,
            by_revenue=by_revenue,
            by_ltv=by_ltv,
            by_capacity=by_capacity,
            final=final,
            by_turnover=by_turnover,
            by_grade=by_grade,
            by_group=by_group,
            binding=binding,
        )
        return max_payment

    def _turnover_limit(self) -> Decimal | None:
        """policy_v3: не больше k × обороты по счёту за год (выписка)."""
        k = self._c.turnover_multiplier
        if k is None:
            return None
        cashflow = self._in.cashflow
        inflow = cashflow.annual_inflow if cashflow is not None else None
        if inflow is None:
            self._hit("limits.turnover", False, "выписки нет — по оборотам не ограничиваем")
            return None
        limit = (k * inflow).quantize(_CENT, rounding=ROUND_DOWN)
        self._hit(
            "limits.turnover",
            limit < self._in.request.amount,
            f"k {k} × обороты по счёту за год {_num(inflow)} = {_num(limit)}",
        )
        return limit

    def _grade_limit(self, grade: Grade) -> Decimal | None:
        if not self._c.grade_max_amount:
            return None
        limit = self._c.grade_max_amount.get(grade, _ZERO).quantize(_CENT)
        self._hit(
            "limits.grade",
            limit < self._in.request.amount,
            f"максимум для грейда {grade}: {_num(limit)}",
        )
        return limit

    def _group_limit(self) -> Decimal | None:
        """policy_v3: потолок на группу заёмщика минус долг по её действующим кредитам. Связанных
        компаний в данных нет — группа это сама компания, долг — остаток по БКИ."""
        ceiling = self._c.group_exposure_max
        if ceiling is None:
            return None
        debt = self._in.bureau.debt_balance
        if debt is None:
            self._hit("limits.group", False, "БКИ недоступно — долг группы неизвестен")
            return None
        limit = max(ceiling - debt, _ZERO).quantize(_CENT)
        self._hit(
            "limits.group",
            limit < self._in.request.amount,
            f"потолок на группу {_num(ceiling)} − долг по кредитам {_num(debt)} = {_num(limit)}",
        )
        return limit

    def _max_payment(self) -> Decimal:
        """Платёж ≤ доли свободного денежного потока; поток по выписке приоритетнее отчёта."""
        company, bureau, cashflow = self._in.company, self._in.bureau, self._in.cashflow
        debts = bureau.monthly_payments
        if cashflow is not None:
            free = cashflow.average_monthly_net - debts
            self._hit(
                "limits.free_cash_flow",
                True,
                f"по выписке: средний чистый поток {_num(cashflow.average_monthly_net)} − "
                f"платежи по кредитам {_num(debts)} = {_num(free)} в месяц",
            )
        else:
            revenue = company.declared_revenue or company.reported_revenue
            if revenue is None:
                free = -debts
                self._hit("limits.free_cash_flow", True, "выручки нет — поток не подтверждён")
            else:
                expenses = company.declared_expenses if company.declared_revenue else None
                if expenses is None:
                    expenses = revenue * self._c.assumed_expense_ratio
                    self._hit(
                        "limits.expenses_assumption",
                        True,
                        f"в отчёте нет расходов — принимаем {self._c.assumed_expense_ratio} "
                        f"выручки: {_num(expenses)}",
                    )
                free = (revenue - expenses) / _TWELVE - debts
                self._hit(
                    "limits.free_cash_flow",
                    True,
                    f"по отчёту: ({_num(revenue)} − {_num(expenses)}) / 12 − платежи по кредитам "
                    f"{_num(debts)} = {_num(free)} в месяц",
                )
        payment = (self._c.payment_share * free).quantize(_CENT, rounding=ROUND_DOWN)
        return max(payment, _ZERO)

    def _clamp_term(self, term: int) -> int:
        product = self._in.product
        return min(max(term, product.term_min_months), product.term_max_months)

    # --- 5. маршрутизация ------------------------------------------------------------------------

    def _routing(self, score: ScoreInput) -> tuple[ReasonCode, ...]:
        product, request, company = self._in.product, self._in.request, self._in.company
        reasons: list[ReasonCode] = []

        over_limit = request.amount > product.auto_decision_limit
        self._hit(
            "route.auto_decision_limit",
            over_limit,
            f"сумма {_num(request.amount)}, лимит автоматического решения "
            f"{_num(product.auto_decision_limit)}",
        )
        if over_limit:
            reasons.append(ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT)

        # В policy_v3 грейд направляет к человеку матрица грейд × сумма.
        if self._c.manual_review_grades:
            grade_review = score.grade in self._c.manual_review_grades
            self._hit("route.grade", grade_review, f"грейд {score.grade}")
            if grade_review:
                reasons.append(ReasonCode.ROUTE_GRADE_D)

        if self._c.route_tax_arrears:
            arrears = company.tax_arrears
            in_arrears = arrears is not None and arrears > 0
            self._hit(
                "route.tax_arrears",
                in_arrears,
                "ФНС не ответила — проверка не выполнена"
                if arrears is None
                else f"недоимка по налогам {_num(arrears)}",
            )
            if in_arrears:
                reasons.append(ReasonCode.ROUTE_TAX_ARREARS)

        flags = set(score.flags)
        if company.verification_status == "mismatch":
            flags.add("verification_mismatch")
        if company.mass_address:
            flags.add("mass_address")
        if self._in.sources_failed or not self._in.bureau.available:
            flags.add("bureau_unavailable")
        for flag, reason in self._c.routing_flags.items():
            matched = flag in flags
            detail = f"флаг {flag}" if matched else f"флага {flag} нет"
            if flag == "bureau_unavailable" and self._in.sources_failed:
                detail = f"не ответили источники: {', '.join(self._in.sources_failed)}"
            self._hit(f"route.{flag}", matched, detail)
            if matched and reason not in reasons:
                reasons.append(reason)

        thin = "thin_file" in flags
        self._hit("route.thin_file", False, "тонкое досье не маршрутизирует" if thin else "нет")
        return tuple(reasons)

    # --- policy_v3: мягкие триггеры и матрица грейд × сумма --------------------------------------

    def _soft_triggers(self) -> None:
        """Не стоп-факторы, а поводы, чтобы заявку посмотрел человек: недоимка, недавняя смена
        руководителя, «разгон» оборотов по выписке. Каждое правило — только если оно в YAML."""
        company = self._in.company
        if self._c.trigger_tax_arrears:
            arrears = company.tax_arrears
            matched = arrears is not None and arrears > 0
            detail = (
                "ФНС не ответила — проверка не выполнена"
                if arrears is None
                else f"недоимка по налогам {_num(arrears)}"
            )
            self._trigger("tax_arrears", matched, detail)

        months = self._c.trigger_head_change_months
        if months is not None:
            tenure = company.head_tenure_months
            if tenure is None:
                matched = False
                detail = "ЕГРЮЛ не сообщил дату записи о руководителе — проверка не выполнена"
            elif company.head_since_registration:
                matched = False
                detail = "руководитель по ЕГРЮЛ не менялся с регистрации"
            else:
                matched = tenure < months
                detail = f"руководитель сменился {tenure} мес. назад (ЕГРЮЛ), порог < {months}"
            self._trigger("head_change", matched, detail)

        recent, ratio = self._c.trigger_turnover_months, self._c.trigger_turnover_ratio
        if recent is not None and ratio is not None:
            self._turnover_spike(recent, ratio)

    def _turnover_spike(self, recent: int, ratio: Decimal) -> None:
        cashflow = self._in.cashflow
        inflows = cashflow.monthly_inflows if cashflow is not None else ()
        if len(inflows) < recent * 2:
            self._trigger(
                "turnover_spike",
                False,
                "выписки нет или она короче двух периодов — проверка не выполнена",
            )
            return
        last = sum(inflows[-recent:], _ZERO) / recent
        earlier = inflows[:-recent]
        before = sum(earlier, _ZERO) / len(earlier)
        growth = last / before if before > 0 else None
        matched = growth is not None and growth > ratio
        shown = f"{growth.quantize(_CENT)}" if growth is not None else "—"
        self._trigger(
            "turnover_spike",
            matched,
            f"поступления за последние {recent} мес. в среднем {_num(last)} против {_num(before)} "
            f"раньше: ×{shown}, порог > ×{ratio}",
        )

    def _trigger(self, code: str, matched: bool, detail: str) -> None:
        self._hit(f"trigger.{code}", matched, detail)
        if matched:
            self._triggers.append(Trigger(code, detail))

    def _risk_matrix(self, grade: Grade) -> MatrixVerdict | None:
        if not self._c.risk_matrix:
            return None
        if self._in.product.code in self._c.startup_products:
            self._hit(
                "strategy.risk_matrix",
                False,
                "продукт для стартапа: вместо матрицы — проектная оценка андеррайтером",
            )
            return None
        band = self._c.band(grade)
        amount = self._in.request.amount
        if band is None:
            self._hit("strategy.risk_matrix", True, f"грейда {grade} нет в матрице — отказ")
            return "reject"
        verdict = band.verdict(amount)
        manual = "без ограничения" if band.manual_up_to is None else f"до {_num(band.manual_up_to)}"
        outcome = {"approve": "автоматическое решение", "manual": "ручная проверка"}.get(
            verdict, "отказ"
        )
        self._hit(
            "strategy.risk_matrix",
            verdict != "approve",
            f"грейд {grade} (корзина {band.label}), сумма {_num(amount)}: автоматика до "
            f"{_num(band.approve_up_to)}, ручная {manual} → {outcome}",
        )
        return verdict

    # --- кассовый разрыв -------------------------------------------------------------------------

    def _cash_gap(self, score: ScoreInput) -> tuple[bool, AlternativeInput | None]:
        """Ожидается ли разрыв и какой продукт под него подходит (None — нечего предложить)."""
        cashflow = self._in.cashflow
        gap = "cash_gap" in score.flags or (cashflow is not None and cashflow.gap_detected)
        if not gap:
            self._hit("cash_gap.forecast", False, "кассовый разрыв не прогнозируется")
            return False, None
        alternative = self._pick(self._c.cash_gap_products)
        month = cashflow.gap_month if cashflow is not None else None
        self._hit(
            "cash_gap.forecast",
            True,
            f"по выписке прогнозируется разрыв в {month or 'ближайшие месяцы'}; альтернатива: "
            + (alternative.code if alternative else "нет подходящего продукта"),
        )
        return True, alternative

    def _pick(self, codes: tuple[str, ...]) -> AlternativeInput | None:
        by_code = {a.code: a for a in self._in.alternatives}
        for code in codes:
            candidate = by_code.get(code)
            if candidate is not None and candidate.eligible and code != self._in.product.code:
                return candidate
        return None

    # --- 6. исход --------------------------------------------------------------------------------

    def _outcome(
        self,
        rate: Decimal,
        max_payment: Decimal,
        gap: bool,
        gap_alternative: AlternativeInput | None,
    ) -> PolicyDecision:
        product, request = self._in.product, self._in.request
        limits = self._limits
        gap_codes = (ReasonCode.CASH_GAP_FORECAST,) if gap else ()
        ceiling = min(
            v
            for v in (
                request.amount,
                limits.by_product,
                limits.by_revenue,
                limits.by_ltv,
                limits.by_turnover,
                limits.by_grade,
                limits.by_group,
            )
            if v is not None
        )
        term_in_product = product.term_min_months <= request.term_months <= product.term_max_months
        fits = annuity_payment(request.amount, self._clamp_term(request.term_months), rate)
        if term_in_product and ceiling >= request.amount and fits <= max_payment:
            self._hit(
                "outcome.approve",
                True,
                f"{_num(request.amount)} на {request.term_months} мес. под {_pct(rate)}, "
                f"платёж {_num(fits)} ≤ {_num(max_payment)}",
            )
            terms = self._terms(request.amount, request.term_months, rate, gap_alternative)
            return self._result(
                "APPROVE", gap_codes, terms=terms, alternative=gap_alternative, gap=gap_alternative
            )

        amount, term, capacity_bound = self._fit(ceiling, rate, max_payment)
        limit_codes = self._limit_codes()
        if amount >= product.amount_min:
            term_codes = (ReasonCode.TERM_ADJUSTED,) if term != request.term_months else ()
            primary = self._primary_limit(ceiling, capacity_bound)
            self._hit(
                "outcome.counter_offer",
                True,
                f"{_num(amount)} на {term} мес. под {_pct(rate)} вместо "
                f"{_num(request.amount)} на {request.term_months} мес.",
            )
            explain = (
                *((primary,) if primary is not None and amount < request.amount else ()),
                *term_codes,
                *gap_codes,
            )
            return self._result(
                "COUNTER_OFFER",
                (*limit_codes, *term_codes, *gap_codes),
                terms=self._terms(amount, term, rate, gap_alternative),
                alternative=gap_alternative,
                gap=gap_alternative,
                explain=explain,
                values={"amount": rub(amount), "term": str(term)},
            )

        alternative = self._reject_alternative(amount, gap_alternative)
        self._hit(
            "outcome.reject",
            True,
            f"лимит {_num(amount)} ниже минимума продукта {_num(product.amount_min)}; "
            f"альтернатива: {alternative.code if alternative else 'нет'}",
        )
        return self._result(
            "REJECT",
            (ReasonCode.LIMIT_BELOW_PRODUCT_MIN, *limit_codes, *gap_codes),
            alternative=alternative,
            gap=gap_alternative,
            explain=(ReasonCode.LIMIT_BELOW_PRODUCT_MIN, *gap_codes),
        )

    def _fit(
        self, ceiling: Decimal, rate: Decimal, max_payment: Decimal
    ) -> tuple[Decimal, int, bool]:
        """Встречное предложение: наибольшая сумма до `ceiling` и кратчайший срок от
        запрошенного, при котором платёж проходит платёжеспособность. Третье значение —
        сумму ограничила платёжеспособность (даже на максимальном сроке)."""
        product = self._in.product
        step = self._c.amount_step
        target = round_down(ceiling, step)
        start = self._clamp_term(self._in.request.term_months)
        for term in range(start, product.term_max_months + 1):
            if target > 0 and annuity_payment(target, term, rate) <= max_payment:
                self._hit("outcome.term_fit", term != start, f"срок {term} мес.")
                return target, term, False
        term = product.term_max_months
        by_capacity = max_principal(max_payment, term, rate)
        amount = round_down(min(by_capacity, ceiling), step)
        while amount > 0 and annuity_payment(amount, term, rate) > max_payment:
            amount -= step
        self._hit(
            "outcome.term_fit",
            term != start,
            f"даже при максимальном сроке {term} мес. платёж проходит только до "
            f"{_num(by_capacity)}",
        )
        return amount, term, True

    def _limit_codes(self) -> tuple[ReasonCode, ...]:
        """Лимиты ниже запрошенной суммы — в причины решения."""
        amount = self._in.request.amount
        limits = self._limits
        pairs = (
            (limits.by_revenue, ReasonCode.LIMIT_BY_REVENUE),
            (limits.by_turnover, ReasonCode.LIMIT_BY_TURNOVER),
            (limits.by_ltv, ReasonCode.LIMIT_BY_LTV),
            (limits.by_capacity, ReasonCode.LIMIT_BY_PAYMENT_CAPACITY),
            (limits.by_grade, ReasonCode.LIMIT_BY_GRADE),
            (limits.by_group, ReasonCode.LIMIT_BY_GROUP),
            (limits.by_product, ReasonCode.LIMIT_BY_PRODUCT),
        )
        return tuple(code for value, code in pairs if value is not None and value < amount)

    def _primary_limit(self, ceiling: Decimal, capacity_bound: bool) -> ReasonCode | None:
        """Какой лимит определил сумму встречного предложения — его текст видит клиент."""
        limits = self._limits
        if capacity_bound:
            return ReasonCode.LIMIT_BY_PAYMENT_CAPACITY
        candidates = (
            (limits.by_revenue, ReasonCode.LIMIT_BY_REVENUE),
            (limits.by_turnover, ReasonCode.LIMIT_BY_TURNOVER),
            (limits.by_ltv, ReasonCode.LIMIT_BY_LTV),
            (limits.by_grade, ReasonCode.LIMIT_BY_GRADE),
            (limits.by_group, ReasonCode.LIMIT_BY_GROUP),
            (limits.by_product, ReasonCode.LIMIT_BY_PRODUCT),
        )
        for value, code in candidates:
            if value is not None and value == ceiling:
                return code
        return None

    def _reject_alternative(
        self, limit: Decimal, gap_alternative: AlternativeInput | None
    ) -> AlternativeInput | None:
        """Есть залог, а продукт беззалоговый → кредит под залог; разрыв → продукт под него;
        иначе — продукт на небольшую сумму, если лимит до его минимума дотягивает."""
        if self._in.collateral is not None and not self._in.product.collateral_required:
            secured = self._pick((self._c.secured_product,))
            if secured is not None:
                return secured
        if gap_alternative is not None:
            return gap_alternative
        small = self._pick((self._c.small_amount_product,))
        if small is not None and limit >= small.amount_min:
            return small
        return None

    # --- сборка итога ----------------------------------------------------------------------------

    def _terms(
        self,
        amount: Decimal,
        term: int,
        rate: Decimal,
        gap_alternative: AlternativeInput | None,
    ) -> OfferTerms:
        product, collateral = self._in.product, self._in.collateral
        conditions = self._x.conditions
        items: list[str] = []
        if collateral is not None:
            items.append(
                render(
                    conditions["collateral"],
                    {"collateral": self._x.collateral_name(collateral.type)},
                )
            )
        if product.guarantee == "owner" or (
            product.guarantee == "none" and self._guarantee_needed(amount)
        ):
            items.append(conditions["guarantee_owner"])
        elif product.guarantee == "msp_corporation":
            items.append(conditions["guarantee_msp_corporation"])
        if product.target_use_confirmation:
            items.append(conditions["target_use"])
        if gap_alternative is not None:
            items.append(render(conditions["cash_gap"], self._values(gap_alternative)))
        return OfferTerms(
            amount=amount,
            term_months=term,
            rate=rate,
            schedule_type=product.repayment_options[0] if product.repayment_options else "annuity",
            conditions=tuple(items),
        )

    def _guarantee_needed(self, amount: Decimal) -> bool:
        """policy_v3: поручительство собственника для слабых грейдов и крупных сумм."""
        grades, above = self._c.guarantee_grades, self._c.guarantee_amount_above
        if not grades and above is None:
            return False
        grade = self._in.score.grade if self._in.score is not None else None
        by_grade = grade in grades
        by_amount = above is not None and amount > above
        needed = by_grade or by_amount
        threshold = f"сумма > {_num(above)}" if above is not None else "по сумме — нет"
        self._hit(
            "offer.guarantee",
            needed,
            f"грейд {grade}, {_num(amount)}: поручительство для грейдов "
            f"{', '.join(sorted(grades)) or '—'} или {threshold}",
        )
        return needed

    def _values(
        self, alternative: AlternativeInput | None, extra: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        cashflow = self._in.cashflow
        values = {
            "requested_amount": rub(self._in.request.amount),
            "amount": rub(self._in.request.amount),
            "term": str(self._in.request.term_months),
            "month": month_in(cashflow.gap_month if cashflow is not None else None),
            "product": self._x.product_name(alternative.code) if alternative else "",
        }
        values.update(extra or {})
        return values

    def _result(
        self,
        outcome: Outcome,
        reasons: tuple[ReasonCode, ...],
        *,
        terms: OfferTerms | None = None,
        alternative: AlternativeInput | None = None,
        gap: AlternativeInput | None = None,
        requested_info: InfoNeed | None = None,
        explain: tuple[ReasonCode, ...] | None = None,
        values: Mapping[str, str] | None = None,
    ) -> PolicyDecision:
        """`gap` — продукт под кассовый разрыв (его называет текст о разрыве), `alternative` —
        итоговая альтернатива решения; при отказе это может быть и другой продукт."""
        rendered = self._values(gap, values)
        explained = reasons if explain is None else explain
        sentences = [self._x.outcomes[outcome]]
        for code in explained:
            if code == ReasonCode.CASH_GAP_FORECAST and gap is None:
                sentences.append(render(self._x.notes["cash_gap_no_alternative"], rendered))
            else:
                sentences.append(render(self._x.reasons[code].text, rendered))
        gap_named = gap is not None and ReasonCode.CASH_GAP_FORECAST in explained
        if alternative is not None and not (gap_named and alternative == gap):
            sentences.append(render(self._x.notes["alternative"], self._values(alternative)))

        hints: list[str] = []
        for code in reasons:
            hint = self._x.reasons[code].hint
            if hint:
                hints.append(render(hint, rendered))
        if self._in.score is not None:
            hints.extend(self._in.score.client_hints)

        return PolicyDecision(
            policy_version=self._c.version,
            key_rate=self._key_rate,
            outcome=outcome,
            terms=terms,
            alternative_product_code=alternative.code if alternative else None,
            reason_codes=tuple(dict.fromkeys(reasons)),
            client_explanation=" ".join(s for s in dict.fromkeys(sentences) if s),
            improvement_hints=tuple(dict.fromkeys(hints))[:_MAX_HINTS],
            requested_info=requested_info,
            rule_trace=tuple(self._trace),
            limits=self._limits,
            rate=self._rate,
            triggers=tuple(self._triggers),
            rate_breakdown=self._rate_breakdown,
        )

    def _hit(self, rule: str, matched: bool, detail: str) -> None:
        self._trace.append(RuleHit(rule, matched, detail))
