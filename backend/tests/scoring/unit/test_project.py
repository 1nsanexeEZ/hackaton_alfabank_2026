"""Проектная оценка стартапа по финмодели: каждое правило на границе, максимальная сумма —
наибольшая, при которой проходят DSCR, свои средства и покрытие; пороги — из project_v1.yaml."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.scoring.application.model_versions import FixedModel
from src.modules.scoring.domain.project import ProjectInput
from src.modules.scoring.facade import ProjectDTO
from src.modules.scoring.infrastructure.config_loader import (
    ScorecardConfigError,
    load_pd_model,
    load_project,
    load_project_file,
)
from src.modules.scoring.infrastructure.facade_impl import ScoringFacadeImpl

PROJECT = load_project()
# Выручка 1 млн и расходы 800 тыс. в месяц: поток 4,8 млн за 24 месяца. Кредит 3 млн на 36 мес.
# под 26%: платёж 120 871,86, за горизонт — 2 900 924,64, DSCR 1,65. Свои 1 млн — 25%
# финансирования, гарантия господдержки на половину кредита.
PLAN = ProjectInput(
    monthly_revenue=(Decimal("1000000"),) * 24,
    monthly_expenses=(Decimal("800000"),) * 24,
    own_funds=Decimal("1000000"),
    collateral_value=Decimal("0"),
    guarantee_share=Decimal("0.5"),
    amount=Decimal("3000000"),
    term_months=36,
    rate=Decimal("26"),
    okved_main="62.01",
    prescreen_passed=True,
)


def failed(project: ProjectInput) -> list[str]:
    return [r.code for r in PROJECT.assess(project).reasons if not r.passed]


def test_a_sound_plan_passes() -> None:
    output = PROJECT.assess(PLAN)
    assert output.passed and output.version == "project_v1"
    assert [r.code for r in output.reasons] == [
        "founder_prescreen",
        "industry",
        "dscr",
        "own_funds",
        "coverage",
    ]
    assert output.metrics.cash_flow == Decimal("4800000.00")
    assert output.metrics.debt_service == Decimal("2900924.64")
    assert output.metrics.dscr == Decimal("1.65")
    assert output.metrics.own_share == Decimal("0.2500")
    assert output.metrics.coverage == Decimal("0.5000")
    # DSCR ограничивает сильнее своих средств (4 млн), гарантия покрывает любую сумму.
    assert output.max_amount == Decimal("3818411.03")


def test_max_amount_is_the_largest_that_passes() -> None:
    top = PROJECT.assess(PLAN).max_amount
    assert PROJECT.assess(replace(PLAN, amount=top)).passed
    assert failed(replace(PLAN, amount=top + Decimal("1000"))) == ["dscr"]


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"monthly_expenses": (Decimal("845000"),) * 24}, "dscr"),
        ({"own_funds": Decimal("749999")}, "own_funds"),
        # (1 млн × 0,7 + 0,2 × 3 млн) / 3 млн ≈ 0,43
        ({"guarantee_share": Decimal("0.2"), "collateral_value": Decimal("1000000")}, "coverage"),
    ],
)
def test_each_amount_rule_fails_past_its_threshold(overrides: dict[str, object], code: str) -> None:
    project = replace(PLAN, **overrides)  # type: ignore[arg-type]
    output = PROJECT.assess(project)
    assert not output.passed
    assert failed(project) == [code]
    # Сумма, которую проект выдерживает, меньше запрошенной, но есть.
    assert Decimal(0) < output.max_amount < PLAN.amount


@pytest.mark.parametrize(
    "overrides",
    [
        {"monthly_expenses": (Decimal("830000"),) * 24},  # DSCR 1,32
        {"own_funds": Decimal("750000")},  # ровно 20%
        {"guarantee_share": Decimal("0"), "collateral_value": Decimal("2142858")},  # 0,5
    ],
)
def test_thresholds_themselves_pass(overrides: dict[str, object]) -> None:
    assert PROJECT.assess(replace(PLAN, **overrides)).passed  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"prescreen_passed": False}, "founder_prescreen"),
        ({"okved_main": "41.20"}, "industry"),
    ],
)
def test_no_amount_without_the_founder_or_in_a_risky_industry(
    overrides: dict[str, object], code: str
) -> None:
    project = replace(PLAN, **overrides)  # type: ignore[arg-type]
    output = PROJECT.assess(project)
    assert failed(project) == [code]
    assert output.max_amount == 0


def test_no_cash_flow_no_amount() -> None:
    project = replace(PLAN, monthly_expenses=(Decimal("1000000"),) * 24)
    output = PROJECT.assess(project)
    assert failed(project) == ["dscr"]
    assert output.metrics.dscr == 0
    assert output.max_amount == 0


def test_collateral_limits_the_amount_with_its_discount() -> None:
    # Залог 2 млн × 0,7 = 1,4 млн покрывает половину кредита до 2,8 млн.
    project = replace(PLAN, guarantee_share=Decimal("0"), collateral_value=Decimal("2000000"))
    output = PROJECT.assess(project)
    assert failed(project) == ["coverage"]
    assert output.max_amount == Decimal("2800000.00")


def test_guarantee_counts_up_to_its_ceiling() -> None:
    # Гарантия на 90% учитывается как 50%: залог по-прежнему нужен для покрытия выше.
    generous = PROJECT.assess(replace(PLAN, guarantee_share=Decimal("0.9")))
    assert generous.metrics.coverage == Decimal("0.5000")


def test_only_the_horizon_counts() -> None:
    longer = replace(
        PLAN,
        monthly_revenue=(*PLAN.monthly_revenue, Decimal("9000000")),
        monthly_expenses=(*PLAN.monthly_expenses, Decimal("0")),
    )
    assert PROJECT.assess(longer) == PROJECT.assess(PLAN)


def test_a_short_loan_is_paid_within_the_horizon() -> None:
    output = PROJECT.assess(replace(PLAN, term_months=12, amount=Decimal("1000000")))
    # 12 платежей по 95 530,14 за горизонт, а не 24.
    assert output.metrics.debt_service == Decimal("1146361.68")


def test_the_model_needs_every_month() -> None:
    with pytest.raises(ValueError):
        PROJECT.assess(replace(PLAN, monthly_revenue=PLAN.monthly_revenue[:23]))


def test_client_messages_carry_no_thresholds() -> None:
    bad = replace(
        PLAN,
        monthly_expenses=(Decimal("990000"),) * 24,
        own_funds=Decimal("1"),
        guarantee_share=Decimal("0"),
        okved_main="68.10",
        prescreen_passed=False,
    )
    output = PROJECT.assess(bad)
    assert not any(r.passed for r in output.reasons)
    for reason in output.reasons:
        assert not any(ch.isdigit() for ch in reason.message), reason.message


def test_facade_maps_the_assessment() -> None:
    facade = ScoringFacadeImpl(None, FixedModel(load_pd_model()))  # type: ignore[arg-type]
    result = facade.assess_project(
        ProjectDTO(
            monthly_revenue=PLAN.monthly_revenue,
            monthly_expenses=PLAN.monthly_expenses,
            own_funds=PLAN.own_funds,
            collateral_value=PLAN.collateral_value,
            guarantee_share=PLAN.guarantee_share,
            amount=PLAN.amount,
            term_months=PLAN.term_months,
            rate=PLAN.rate,
            okved_main=PLAN.okved_main,
            prescreen_passed=PLAN.prescreen_passed,
        )
    )
    assert result.passed and result.version == "project_v1"
    assert result.max_amount == Decimal("3818411.03")
    assert result.dscr == Decimal("1.65") and result.own_share == Decimal("0.2500")
    assert {r.code for r in result.reasons} == {
        "founder_prescreen",
        "industry",
        "dscr",
        "own_funds",
        "coverage",
    }


def test_broken_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "project.yaml"
    path.write_text("version: x\nhorizon_months: 0\n", encoding="utf-8")
    with pytest.raises(ScorecardConfigError):
        load_project_file(path)
