"""Границы корзин каждого фактора (ровно на границе — в какую корзину) и поведение
при отсутствии данных: фактор нейтрален, скоринг не штрафует за наш сбой."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    Factor,
    RequestInput,
    ScoringInput,
    TaxInput,
)
from src.scoring.infrastructure.config_loader import load_scorecard

_CARD = load_scorecard()


def _inp(**over: Any) -> ScoringInput:
    base: dict[str, Any] = {
        "amount": "1000000",
        "term": 12,
        "rate": "21.5",
        "product": "UNSECURED",
        "facility": "term_loan",
        "legal_form": "LLC",
        "age": 36,
        "okved": "62.01",
        "verif": "verified",
        "status": "active",
        "declared": "12000000",
        "prev": "12000000",
        "declared_debt": None,
        "arrears": "0",
        "reported": "12000000",
        "avail": True,
        "has_hist": True,
        "overdue": 0,
        "inq": 0,
        "bki": "0",
        "collat": None,
        "cf": CashflowInput(False, None, None, None, None),
        "mass": False,
        "srcfail": (),
    }
    base.update(over)

    def d(value: str | None) -> Decimal | None:
        return Decimal(value) if value is not None else None

    return ScoringInput(
        request=RequestInput(
            Decimal(base["amount"]),
            base["term"],
            base["product"],
            base["facility"],
            Decimal(base["rate"]),
        ),
        company=CompanyInput(
            base["legal_form"],
            base["age"],
            base["okved"],
            base["verif"],
            base["status"],
            d(base["declared"]),
            d(base["prev"]),
            d(base["declared_debt"]),
        ),
        tax=TaxInput(d(base["arrears"]), d(base["reported"])),
        bureau=BureauInput(
            base["avail"], base["has_hist"], base["overdue"], base["inq"], Decimal(base["bki"])
        ),
        collateral=CollateralInput(d(base["collat"])),
        cashflow=base["cf"],
        mass_address=base["mass"],
        sources_failed=base["srcfail"],
        as_of=date(2026, 10, 21),
    )


def _factor(inp: ScoringInput, code: str) -> Factor:
    return next(f for f in _CARD.calculate(inp).factors if f.code == code)


def _points(inp: ScoringInput, code: str) -> int:
    return _factor(inp, code).points


def test_business_age_bucket_boundaries() -> None:
    assert _points(_inp(age=11), "business_age") == -10
    assert _points(_inp(age=12), "business_age") == 0
    assert _points(_inp(age=23), "business_age") == 0
    assert _points(_inp(age=24), "business_age") == 30
    assert _points(_inp(age=60), "business_age") == 30
    assert _points(_inp(age=61), "business_age") == 50


def test_revenue_trend_boundaries() -> None:
    assert _points(_inp(declared="80", prev="100"), "revenue_trend") == -10  # −20% ровно → −20…0
    assert _points(_inp(declared="79", prev="100"), "revenue_trend") == -50  # −21% → <−20%
    assert _points(_inp(declared="90", prev="100"), "revenue_trend") == -10  # −10%
    assert _points(_inp(declared="120", prev="100"), "revenue_trend") == 20  # +20% ровно → 0…20
    assert _points(_inp(declared="121", prev="100"), "revenue_trend") == 40  # +21% → >20%
    assert _factor(_inp(prev=None), "revenue_trend").direction == "neutral"


def test_bureau_overdue_boundaries_and_missing() -> None:
    assert _points(_inp(overdue=0), "bureau_overdue") == 40
    assert _points(_inp(overdue=30), "bureau_overdue") == -30
    assert _points(_inp(overdue=31), "bureau_overdue") == -120
    assert _points(_inp(overdue=90), "bureau_overdue") == -120
    assert _points(_inp(overdue=91), "bureau_overdue") == -200
    # тонкое досье: истории нет → −10 и флаг thin_file, но has_data False
    thin = _factor(_inp(has_hist=False), "bureau_overdue")
    assert thin.points == -10 and thin.has_data is False
    assert "thin_file" in _CARD.calculate(_inp(has_hist=False)).flags
    # источник недоступен → нейтрально, не штрафуем
    down = _factor(_inp(avail=False), "bureau_overdue")
    assert down.direction == "neutral" and down.has_data is False
    assert "bureau_unavailable" in _CARD.calculate(_inp(avail=False)).flags


def test_bureau_inquiries_boundaries() -> None:
    assert _points(_inp(inq=2), "bureau_inquiries") == 0
    assert _points(_inp(inq=3), "bureau_inquiries") == -15
    assert _points(_inp(inq=5), "bureau_inquiries") == -15
    assert _points(_inp(inq=6), "bureau_inquiries") == -40


def test_tax_arrears() -> None:
    assert _points(_inp(arrears="0"), "tax_arrears") == 10
    assert _points(_inp(arrears="1"), "tax_arrears") == -60
    assert _factor(_inp(arrears=None), "tax_arrears").direction == "neutral"


def test_amount_to_revenue_boundaries() -> None:
    assert _points(_inp(amount="900000", declared="10000000"), "amount_to_revenue") == 30  # 0.09
    assert (
        _points(_inp(amount="1000000", declared="10000000"), "amount_to_revenue") == 0
    )  # 0.1 ровно
    assert (
        _points(_inp(amount="3000000", declared="10000000"), "amount_to_revenue") == -40
    )  # 0.3 ровно
    assert _points(_inp(amount="5000000", declared="10000000"), "amount_to_revenue") == -40  # 0.5


def test_revenue_consistency_boundaries_and_flag() -> None:
    assert _points(_inp(declared="100", reported="85"), "revenue_consistency") == 10  # 15%
    assert _points(_inp(declared="100", reported="70"), "revenue_consistency") == -20  # 30%
    big = _inp(declared="100", reported="60")  # 40%
    assert _points(big, "revenue_consistency") == -60
    assert "revenue_mismatch" in _CARD.calculate(big).flags
    assert _factor(_inp(reported=None), "revenue_consistency").direction == "neutral"


def test_verification_variants() -> None:
    assert _points(_inp(verif="verified"), "verification") == 10
    assert _points(_inp(verif="mismatch"), "verification") == -30
    assert "verification_mismatch" in _CARD.calculate(_inp(verif="mismatch")).flags
    assert _points(_inp(verif="unverified"), "verification") == 0


def test_collateral_coverage_present_only_when_pledged() -> None:
    codes = {f.code for f in _CARD.calculate(_inp(collat=None)).factors}
    assert "collateral_coverage" not in codes
    assert _points(_inp(amount="1000000", collat="2000000"), "collateral_coverage") == 40
    assert _points(_inp(amount="1000000", collat="1000000"), "collateral_coverage") == 20
    assert _points(_inp(amount="1000000", collat="999999"), "collateral_coverage") == 0


def test_cash_gap_variants() -> None:
    absent = _factor(_inp(cf=CashflowInput(False, None, None, None, None)), "cash_gap")
    assert absent.direction == "neutral" and absent.has_data is False
    gap = _inp(cf=CashflowInput(True, True, "2026-12", Decimal("50000.00"), None))
    assert _points(gap, "cash_gap") == -15
    result = _CARD.calculate(gap)
    assert "cash_gap" in result.flags and result.bank_notes
    no_gap = _inp(cf=CashflowInput(True, False, None, None, True))
    assert _points(no_gap, "cash_gap") == 10


def test_revenue_confirmed_false_flags_mismatch() -> None:
    inp = _inp(cf=CashflowInput(True, False, None, None, False))
    assert "revenue_mismatch" in _CARD.calculate(inp).flags


def test_debt_load_neutral_without_revenue() -> None:
    factor = _factor(_inp(declared=None, reported=None), "debt_load")
    assert factor.direction == "neutral" and factor.has_data is False


def test_data_completeness_drops_with_missing_sources() -> None:
    full = _CARD.calculate(_inp()).data_completeness
    degraded = _CARD.calculate(_inp(avail=False, prev=None)).data_completeness
    assert degraded < full
