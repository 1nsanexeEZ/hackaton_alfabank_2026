"""Правила policy_v2 по одному: стоп-факторы ГИР БО, Контура, ФНС, БКИ руководителя и стоп-листа
банка, маршрут по недоимке. Пороги — из `policy_v2.yaml`; базовая заявка одобряется."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from src.modules.decision.domain.model import (
    AccountingInput,
    BureauInput,
    CounterpartyInput,
    DecisionInput,
    HeadBureauInput,
    PolicyDecision,
    ReasonCode,
    RuleHit,
)
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.test_credit_policy_rules import company, make

POLICY = load_policy("policy_v2")
KEY_RATE = POLICY.config.key_rate_reference
CLEAN = CounterpartyInput(0, Decimal(0), Decimal(0))


def v2(**overrides: Any) -> DecisionInput:
    """Заявка без замечаний во всех новых источниках."""
    base = make(
        company=company(tax_arrears=Decimal(0), account_blocks=0),
        bureau=BureauInput(True, 0, Decimal("180000"), current_overdue_days=0),
        counterparty=CLEAN,
        accounting=AccountingInput(2025, Decimal("48000000"), Decimal("12600000")),
        head_bureau=HeadBureauInput("ok", 0),
    )
    return replace(base, **overrides)


def decide(inp: DecisionInput) -> PolicyDecision:
    return POLICY.decide(inp, key_rate=KEY_RATE)


def hit(decision: PolicyDecision, rule: str) -> RuleHit:
    return next(h for h in decision.rule_trace if h.rule == rule)


def test_clean_application_is_approved() -> None:
    decision = decide(v2())
    assert decision.outcome == "APPROVE" and decision.policy_version == "policy_v2"
    assert not any(h.matched for h in decision.rule_trace if h.rule.startswith("stop."))


def test_v1_rules_do_not_reach_the_trace_of_v1() -> None:
    decision = load_policy("policy_v1").decide(v2(), key_rate=KEY_RATE)
    rules = {h.rule for h in decision.rule_trace}
    assert not rules & {"stop.current_overdue", "stop.head_overdue", "route.tax_arrears"}


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"bureau": BureauInput(True, 30, Decimal(0), current_overdue_days=30)},
            ReasonCode.STOP_CURRENT_OVERDUE,
        ),
        ({"head_bureau": HeadBureauInput("ok", 30)}, ReasonCode.STOP_HEAD_OVERDUE),
        (
            {"company": company(tax_arrears=Decimal(0), account_blocks=1)},
            ReasonCode.STOP_ACCOUNT_BLOCKS,
        ),
        (
            {"company": company(tax_arrears=Decimal("300000.01"), account_blocks=0)},
            ReasonCode.STOP_TAX_ARREARS,
        ),
        (
            {"counterparty": replace(CLEAN, bankruptcy_messages=1)},
            ReasonCode.STOP_BANKRUPTCY_MESSAGE,
        ),
        (
            # 10 % от выручки ГИР БО 48 млн — 4,8 млн.
            {"counterparty": replace(CLEAN, enforcement_sum=Decimal("4800000.01"))},
            ReasonCode.STOP_LARGE_ENFORCEMENT,
        ),
        (
            {"counterparty": replace(CLEAN, lawsuits_sum=Decimal("9600000.01"))},
            ReasonCode.STOP_LARGE_LAWSUITS,
        ),
        (
            {"accounting": AccountingInput(2025, Decimal("48000000"), Decimal("-1"))},
            ReasonCode.STOP_NEGATIVE_EQUITY,
        ),
        (
            {"company": company(tax_arrears=Decimal(0), account_blocks=0, mass_address=True)},
            ReasonCode.STOP_MASS_ADDRESS,
        ),
        (
            {"company": company(tax_arrears=Decimal(0), account_blocks=0, okved_main="92.11")},
            ReasonCode.STOP_FORBIDDEN_OKVED,
        ),
    ],
    ids=[
        "company_overdue_30",
        "head_overdue_30",
        "account_blocks",
        "tax_arrears_above",
        "bankruptcy_message",
        "enforcement_share",
        "lawsuits_share",
        "negative_equity",
        "mass_address",
        "forbidden_okved",
    ],
)
def test_each_stop_factor_rejects(overrides: dict[str, Any], reason: ReasonCode) -> None:
    decision = decide(v2(**overrides))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (reason,)
    assert decision.terms is None and decision.alternative_product_code is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"bureau": BureauInput(True, 29, Decimal(0), current_overdue_days=29)},
        {"head_bureau": HeadBureauInput("ok", 29)},
        {"company": company(tax_arrears=Decimal("300000"), account_blocks=0)},
        {"counterparty": replace(CLEAN, enforcement_sum=Decimal("4800000"))},
        {"counterparty": replace(CLEAN, lawsuits_sum=Decimal("9600000"))},
        {"accounting": AccountingInput(2025, Decimal("48000000"), Decimal("0"))},
    ],
    ids=["company_29", "head_29", "arrears_at_limit", "enforcement_at", "lawsuits_at", "zero"],
)
def test_thresholds_are_not_crossed_at_the_edge(overrides: dict[str, Any]) -> None:
    decision = decide(v2(**overrides))
    assert not any(code.startswith("STOP_") for code in decision.reason_codes)


def test_head_overdue_counts_from_thirty_days_not_ninety() -> None:
    """Схема: текущая просрочка 30+ дней у руководителя — стоп (в roadmap было > 90)."""
    decision = decide(v2(head_bureau=HeadBureauInput("ok", 45)))
    assert decision.reason_codes == (ReasonCode.STOP_HEAD_OVERDUE,)
    assert hit(decision, "stop.head_overdue").detail == (
        "текущая просрочка руководителя 45 дн., порог ≥ 30"
    )


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        ("no_consent", "нет согласия руководителя на запрос его БКИ — проверка не выполнена"),
        ("no_head", "руководитель по реестру не найден среди участников — проверка не выполнена"),
        ("failed", "БКИ руководителя не ответило — проверка не выполнена"),
        ("not_requested", "БКИ руководителя не запрашивалось — проверка не выполнена"),
    ],
)
def test_head_bureau_without_an_answer_does_not_stop(status: str, detail: str) -> None:
    decision = decide(v2(head_bureau=HeadBureauInput(status)))  # type: ignore[arg-type]
    assert decision.outcome == "APPROVE"
    assert hit(decision, "stop.head_overdue") == RuleHit("stop.head_overdue", False, detail)


def test_tax_arrears_below_the_stop_go_to_the_underwriter() -> None:
    decision = decide(v2(company=company(tax_arrears=Decimal("1500"), account_blocks=0)))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_TAX_ARREARS,)
    assert hit(decision, "route.tax_arrears").detail == "недоимка по налогам 1 500"
    assert "задолженность по налогам" in decision.client_explanation


def test_missing_sources_skip_their_checks() -> None:
    decision = decide(
        v2(
            company=company(),  # ФНС не ответила: недоимки и блокировок не знаем
            counterparty=None,
            accounting=None,
            sources_failed=("fns", "kontur"),
        )
    )
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)
    for rule in ("stop.account_blocks", "stop.tax_arrears", "route.tax_arrears"):
        assert hit(decision, rule).detail == "ФНС не ответила — проверка не выполнена"
    for rule in ("stop.bankruptcy_messages", "stop.enforcement", "stop.lawsuits"):
        assert hit(decision, rule).detail == "Контур не ответил — проверка не выполнена"
    assert hit(decision, "stop.negative_equity").detail == (
        "отчётности в ГИР БО нет — проверка не выполнена"
    )


def test_share_thresholds_fall_back_to_tax_revenue() -> None:
    decision = decide(
        v2(accounting=None, counterparty=replace(CLEAN, enforcement_sum=Decimal("4750000.01")))
    )
    assert decision.reason_codes == (ReasonCode.STOP_LARGE_ENFORCEMENT,)
    assert "(ФНС)" in hit(decision, "stop.enforcement").detail


def test_share_thresholds_need_some_revenue() -> None:
    no_revenue = company(
        tax_arrears=Decimal(0), account_blocks=0, declared_revenue=None, reported_revenue=None
    )
    decision = decide(
        v2(
            company=no_revenue,
            accounting=None,
            counterparty=replace(CLEAN, lawsuits_sum=Decimal("1")),
        )
    )
    assert ReasonCode.STOP_LARGE_LAWSUITS not in decision.reason_codes
    assert "выручка неизвестна" in hit(decision, "stop.lawsuits").detail


def test_every_stop_is_listed_together() -> None:
    decision = decide(
        v2(
            company=company(tax_arrears=Decimal("500000"), account_blocks=2),
            counterparty=CounterpartyInput(1, Decimal("9000000"), Decimal("20000000")),
            head_bureau=HeadBureauInput("ok", 60),
        )
    )
    assert decision.reason_codes == (
        ReasonCode.STOP_HEAD_OVERDUE,
        ReasonCode.STOP_ACCOUNT_BLOCKS,
        ReasonCode.STOP_TAX_ARREARS,
        ReasonCode.STOP_BANKRUPTCY_MESSAGE,
        ReasonCode.STOP_LARGE_ENFORCEMENT,
        ReasonCode.STOP_LARGE_LAWSUITS,
    )
