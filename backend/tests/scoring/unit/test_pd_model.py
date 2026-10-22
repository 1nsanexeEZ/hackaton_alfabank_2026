"""PD-модель по шагам схемы: сегмент, бины с «нет данных» и винзоризацией, калибровка в PD,
грейд A–J, коды причин. Golden на демо-сценариях — в test_pd_model_golden.py."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from src.modules.scoring.domain.model import BureauInput, CollateralInput, ScoringInput
from src.modules.scoring.domain.pd_model import Calibration
from src.modules.scoring.infrastructure.config_loader import default_model, load_pd_model
from tests.scoring.scenarios import SCENARIOS

MODEL = load_pd_model()
ROMASHKA = SCENARIOS["romashka_s1"]


def with_company(inp: ScoringInput, **overrides: object) -> ScoringInput:
    return replace(inp, company=replace(inp.company, **overrides))


def test_default_model_is_pd_model_v2() -> None:
    assert default_model().version == "pd_model_v2"


@pytest.mark.parametrize(
    ("legal_form", "age", "segment", "scorecard"),
    [
        ("LLC", 72, "legal_entity", "legal_entity_v1"),
        ("JSC", 6, "legal_entity", "legal_entity_v1"),
        ("IE", 8, "entrepreneur", "entrepreneur_v1"),
        ("LLC", 5, "new_client", "new_client_v1"),
        ("IE", 0, "new_client", "new_client_v1"),
    ],
)
def test_segment_by_turnover_months_and_legal_form(
    legal_form: str, age: int, segment: str, scorecard: str
) -> None:
    out = MODEL.calculate(with_company(ROMASHKA, legal_form=legal_form, business_age_months=age))
    assert (out.segment, out.scorecard) == (segment, scorecard)


def test_new_client_card_is_simplified() -> None:
    out = MODEL.calculate(with_company(ROMASHKA, business_age_months=3))
    codes = {f.code for f in out.factors}
    assert not codes & {"revenue_trend", "revenue_consistency", "cash_gap"}
    assert {"business_age", "debt_load", "bureau_overdue"} <= codes


def test_calibration_doubles_the_odds_every_pdo() -> None:
    calibration = Calibration(score=600, odds=Decimal(15), pdo=50)
    assert calibration.pd(600) == Decimal("0.0625")  # 1 / (1 + 15)
    assert calibration.pd(650) == Decimal("0.0323")  # 1 / (1 + 30)
    assert calibration.pd(800) == Decimal("0.0041")  # 1 / (1 + 240)


def test_higher_score_lower_pd_better_grade() -> None:
    pds = [Calibration(600, Decimal(15), 50).pd(score) for score in range(300, 900, 25)]
    assert pds == sorted(pds, reverse=True)
    grades = [MODEL.grade(pd) for pd in pds]
    assert grades == sorted(grades, reverse=True)


@pytest.mark.parametrize(
    ("pd", "grade"),
    [
        ("0.0049", "A"),
        ("0.0050", "B"),
        ("0.0174", "C"),
        ("0.0399", "E"),
        ("0.0599", "F"),
        ("0.2199", "I"),
        ("0.2200", "J"),
        ("0.9000", "J"),
    ],
)
def test_grade_by_pd_range(pd: str, grade: str) -> None:
    assert MODEL.grade(Decimal(pd)) == grade


def test_romashka_result() -> None:
    out = MODEL.calculate(ROMASHKA)
    assert (out.score, out.pd_12m, out.grade) == (800, Decimal("0.0041"), "A")
    assert out.flags == ()


def test_missing_value_takes_the_no_data_bin() -> None:
    no_previous = with_company(ROMASHKA, declared_revenue_previous=None)
    trend = {f.code: f for f in MODEL.calculate(no_previous).factors}["revenue_trend"]
    assert (trend.value, trend.bin, trend.points, trend.has_data) == (
        None,
        "нет данных",
        -10,
        False,
    )


def test_outliers_are_winsorized_to_the_cap() -> None:
    old = with_company(ROMASHKA, business_age_months=900)
    age = {f.code: f for f in MODEL.calculate(old).factors}["business_age"]
    assert (age.value, age.bin, age.points) == ("900", "≥60", 50)


def test_bureau_outage_is_not_penalized() -> None:
    down = replace(ROMASHKA, bureau=BureauInput(False, False, None, None, Decimal(0)))
    out = MODEL.calculate(down)
    bureau = {f.code: f for f in out.factors}
    assert bureau["bureau_overdue"].points == 0 and bureau["bureau_inquiries"].points == 0
    assert "bureau_unavailable" in out.flags


def test_collateral_feature_only_with_collateral() -> None:
    assert "collateral_coverage" not in {f.code for f in MODEL.calculate(ROMASHKA).factors}
    pledged = replace(ROMASHKA, collateral=CollateralInput(Decimal("9000000")))
    coverage = {f.code: f for f in MODEL.calculate(pledged).factors}["collateral_coverage"]
    assert (coverage.value, coverage.bin, coverage.points) == ("3", "≥2", 40)


def test_reason_codes_are_top_three_lost_points() -> None:
    out = MODEL.calculate(SCENARIOS["zakat_s4"])
    # Просрочка 120 дней: −200 против +40; недоимка: −60 против +10; падение выручки.
    assert out.reason_codes == ("bureau_overdue", "tax_arrears", "revenue_trend")


def test_reason_codes_of_a_clean_company_name_only_what_it_lost() -> None:
    out = MODEL.calculate(ROMASHKA)
    assert out.reason_codes == ("industry_risk", "cash_gap")


def test_flags_match_the_previous_card() -> None:
    assert "revenue_mismatch" in MODEL.calculate(SCENARIOS["progress_s5"]).flags
    assert "verification_mismatch" in MODEL.calculate(SCENARIOS["vector_s3"]).flags
    ivanov = MODEL.calculate(SCENARIOS["ivanov_s2"])
    assert {"thin_file", "cash_gap"} <= set(ivanov.flags)
    assert ivanov.bank_notes and "кассовый разрыв" in ivanov.bank_notes[0]


def test_client_hints_only_for_the_worst_factors() -> None:
    out = MODEL.calculate(SCENARIOS["zakat_s4"])
    hinted = [f.code for f in out.factors if f.client_hint]
    assert 1 <= len(hinted) <= 3
    assert "bureau_overdue" in hinted
