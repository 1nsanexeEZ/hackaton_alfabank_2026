"""Предодобрение: та же политика по облегчённым данным, лимит на грейд осторожнее."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from src.decision.domain.model import PreApprovalInput, ProductInput, SupportProgramInput
from src.decision.infrastructure.config_loader import default_policy

POLICY = default_policy()
KEY_RATE = POLICY.config.key_rate_reference

UNSECURED = ProductInput(
    code="UNSECURED",
    amount_min=Decimal("300000"),
    amount_max=Decimal("30000000"),
    term_min_months=12,
    term_max_months=60,
    rate_base=Decimal("23.5"),
    rate_max=Decimal("30"),
    repayment_options=("annuity", "differentiated"),
    collateral_required=False,
    auto_decision_limit=Decimal("5000000"),
)


def make(**overrides: Any) -> PreApprovalInput:
    base = PreApprovalInput(
        product=UNSECURED,
        grade="A",
        score=790,
        registry_status="active",
        annual_revenue=Decimal("48000000"),
        okved_main="56.10",
        in_msp_registry=True,
    )
    return replace(base, **overrides)


def test_limit_is_one_grade_more_cautious() -> None:
    offer = POLICY.pre_approve(make(), key_rate=KEY_RATE)
    assert offer is not None
    # грейд A → лимит как для B: 0,4 × 48 млн
    assert offer.max_amount == Decimal("19200000.00")
    assert offer.rate_from == Decimal("23.50")  # ставка — по своему грейду
    assert offer.term_max_months == 60
    assert offer.product_code == "UNSECURED"
    assert len(offer.factors_summary) == 3


@pytest.mark.parametrize(("grade", "amount"), [("B", "12000000.00"), ("C", "7200000.00")])
def test_cautious_multiplier_by_grade(grade: str, amount: str) -> None:
    offer = POLICY.pre_approve(make(grade=grade), key_rate=KEY_RATE)
    assert offer is not None and offer.max_amount == Decimal(amount)


@pytest.mark.parametrize(
    "overrides",
    [
        {"grade": "D"},  # на ступень осторожнее — E, стоп-фактор
        {"grade": "E"},
        {"registry_status": "liquidating"},
        {"registry_status": "bankrupt"},
        {"annual_revenue": None},
        {"annual_revenue": Decimal(0)},
        {"grade": "C", "annual_revenue": Decimal("1500000")},  # 0,15 × 1,5 млн < 300 000
    ],
)
def test_nothing_to_offer(overrides: dict[str, Any]) -> None:
    assert POLICY.pre_approve(make(**overrides), key_rate=KEY_RATE) is None


def test_capped_by_product_maximum() -> None:
    offer = POLICY.pre_approve(make(annual_revenue=Decimal("200000000")), key_rate=KEY_RATE)
    assert offer is not None and offer.max_amount == Decimal("30000000.00")


def test_rounded_down_to_ten_thousand() -> None:
    offer = POLICY.pre_approve(make(annual_revenue=Decimal("12345678")), key_rate=KEY_RATE)
    assert offer is not None and offer.max_amount == Decimal("4930000.00")


def test_key_rate_shifts_rate_from() -> None:
    offer = POLICY.pre_approve(make(), key_rate=KEY_RATE + Decimal(2))
    assert offer is not None and offer.rate_from == Decimal("25.50")


@pytest.mark.parametrize(("in_msp", "rate"), [(True, "15.00"), (None, "15.50")])
def test_gov_support_cap_only_when_company_qualifies(in_msp: bool | None, rate: str) -> None:
    gov = replace(
        UNSECURED,
        code="GOV_SUPPORT",
        amount_min=Decimal("1000000"),
        amount_max=Decimal("100000000"),
        rate_base=Decimal("12"),
        rate_max=Decimal("18"),
        support_program=SupportProgramInput("MSP_PRIORITY", Decimal("15"), True, frozenset({"56"})),
    )
    offer = POLICY.pre_approve(
        make(product=gov, grade="C", in_msp_registry=in_msp), key_rate=KEY_RATE
    )
    assert offer is not None and offer.rate_from == Decimal(rate)
