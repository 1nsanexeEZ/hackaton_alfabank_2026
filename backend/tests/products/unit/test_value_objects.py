from decimal import Decimal

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import ValidationError
from src.products.domain import texts
from src.products.domain.value_objects import (
    AmountRange,
    BorrowerProfile,
    DocumentRequirement,
    Eligibility,
    EligibilityCheck,
    EligibilityReason,
    LoanNeed,
    ProcessingProfile,
    ProductCode,
    RateRange,
    SecurityRequirement,
    SupportProgram,
    TermRange,
)


def field_of(error: pytest.ExceptionInfo[ValidationError]) -> str:
    assert error.value.details is not None
    return error.value.details["field"]


def test_product_code() -> None:
    assert str(ProductCode("GOV_SUPPORT")) == "GOV_SUPPORT"
    for bad in ("unsecured", "X", "1LOAN", "CREDIT-LINE", "A" * 33):
        with pytest.raises(ValidationError):
            ProductCode(bad)


def test_amount_range() -> None:
    frame = AmountRange(Money.of(300_000), Money.of(30_000_000))
    assert frame.contains(Money.of(300_000)) and frame.contains(Money.of(30_000_000))
    assert not frame.contains(Money.of(299_999)) and not frame.contains(Money("30000000.01"))
    assert frame.clamp(Money.of(40_000_000)) == Money.of(30_000_000)
    assert frame.clamp(Money.of(1)) == Money.of(300_000)
    assert frame.clamp(Money.of(1_000_000)) == Money.of(1_000_000)


@pytest.mark.parametrize(
    "low,high,field",
    [
        (Money.of(0), Money.of(10), "amount_min"),
        (Money.of(10), Money.of(5), "amount_max"),
    ],
)
def test_amount_range_invariants(low: Money, high: Money, field: str) -> None:
    with pytest.raises(ValidationError) as error:
        AmountRange(low, high)
    assert field_of(error) == field


def test_term_range() -> None:
    frame = TermRange(12, 60)
    assert frame.contains(12) and frame.contains(60) and not frame.contains(61)
    assert frame.clamp(3) == 12 and frame.clamp(84) == 60
    for low, high in ((0, 12), (24, 12), (12, 361)):
        with pytest.raises(ValidationError):
            TermRange(low, high)


def test_rate_range_is_decimal_and_ordered() -> None:
    rates = RateRange(Decimal("23.5"), Decimal("30"))
    assert rates.contains(Decimal("23.5")) and not rates.contains(Decimal("30.01"))
    for base, top in ((Decimal("-1"), Decimal("5")), (Decimal("10"), Decimal("9"))):
        with pytest.raises(ValidationError):
            RateRange(base, top)
    with pytest.raises(ValidationError):
        RateRange(Decimal("5"), Decimal("101"))
    with pytest.raises(ValidationError):
        RateRange(23.5, Decimal("30"))  # type: ignore[arg-type]


def test_security_requirement() -> None:
    optional = SecurityRequirement("optional", ("real_estate",), required_from=Money.of(30_000_000))
    assert not optional.needs_collateral(Money.of(29_999_999))
    assert optional.needs_collateral(Money.of(30_000_000))
    assert not optional.needs_collateral(None)
    assert SecurityRequirement("required", ("vehicle",)).needs_collateral(Money.of(1))
    assert not SecurityRequirement().needs_collateral(Money.of(100_000_000))


@pytest.mark.parametrize(
    "kwargs,field",
    [
        ({"collateral": "maybe"}, "collateral_kind"),
        ({"collateral": "none", "collateral_types": ("vehicle",)}, "collateral_types"),
        ({"collateral": "required"}, "collateral_types"),
        ({"collateral": "required", "collateral_types": ("yacht",)}, "collateral_types"),
        (
            {"collateral": "required", "collateral_types": ("vehicle", "vehicle")},
            "collateral_types",
        ),
        (
            {
                "collateral": "required",
                "collateral_types": ("vehicle",),
                "required_from": Money.of(1),
            },
            "collateral_required_from",
        ),
        ({"guarantee": "friend"}, "guarantee"),
    ],
)
def test_security_requirement_invariants(kwargs: dict, field: str) -> None:
    with pytest.raises(ValidationError) as error:
        SecurityRequirement(**kwargs)
    assert field_of(error) == field


def test_support_program_covers_okved_classes() -> None:
    program = SupportProgram("P", "Программа", Decimal("15"), True, frozenset({"62", "56"}))
    assert program.covers("62") and not program.covers("41")
    assert SupportProgram("P", "Любые отрасли", Decimal("15")).covers("41")
    with pytest.raises(ValidationError):
        SupportProgram("P", "Программа", Decimal("15"), True, frozenset({"62.01"}))


def test_eligibility_invariants() -> None:
    with pytest.raises(ValidationError):
        Eligibility(-1)
    with pytest.raises(ValidationError):
        Eligibility(6, frozenset())
    with pytest.raises(ValidationError):
        Eligibility(6, frozenset({"LTD"}))


def test_document_requirement_conditions() -> None:
    always = DocumentRequirement("bank_statement", "Выписка")
    from_amount = DocumentRequirement("financial_report", "Отчётность", Money.of(5_000_000))
    for_companies = DocumentRequirement("charter", "Устав", legal_forms=frozenset({"LLC", "JSC"}))
    assert always.applies(None, None)
    assert not from_amount.applies(Money.of(4_999_999), "LLC")
    assert from_amount.applies(Money.of(5_000_000), "LLC")
    assert not from_amount.applies(None, "LLC")
    assert for_companies.applies(None, "JSC") and not for_companies.applies(None, "IE")
    with pytest.raises(ValidationError):
        DocumentRequirement("Financial Report", "Отчётность")


def test_processing_profile() -> None:
    profile = ProcessingProfile("express_v1", Money.of(5_000_000))
    assert not profile.requires_manual_review(Money.of(5_000_000))
    assert profile.requires_manual_review(Money("5000000.01"))
    assert ProcessingProfile("mortgage_v1", Money.of(0)).requires_manual_review(Money.of(1))
    with pytest.raises(ValidationError):
        ProcessingProfile("Express", Money.of(1))


def test_borrower_okved_class() -> None:
    borrower = BorrowerProfile("IE", 8, Money.of(6_000_000), "62.01")
    assert borrower.okved_class == "62"
    assert borrower.in_msp_registry is None and borrower.cash_gap_expected is None


def test_eligibility_check_is_all_reasons_passed() -> None:
    ok = EligibilityReason("legal_form", True, "ok")
    bad = EligibilityReason("business_age", False, "no")
    assert EligibilityCheck("X", (ok,)).eligible
    check = EligibilityCheck("X", (ok, bad))
    assert not check.eligible and check.failed == (bad,)


@pytest.mark.parametrize(
    "kwargs,field",
    [
        ({"purpose": "other"}, "purpose"),
        ({"amount": Money.of(0)}, "amount"),
        ({"term_months": 0}, "term_months"),
        ({"term_months": 361}, "term_months"),
    ],
)
def test_loan_need_validation(kwargs: dict, field: str) -> None:
    values = {"purpose": "working_capital", "amount": Money.of(1_000_000), "term_months": 12}
    with pytest.raises(ValidationError) as error:
        LoanNeed(**{**values, **kwargs})
    assert field_of(error) == field


@pytest.mark.parametrize(
    "amount,text",
    [
        ("5000000", "5 млн ₽"),
        ("300000", "300 тыс. ₽"),
        ("1250000", "1,25 млн ₽"),
        ("150000000", "150 млн ₽"),
        ("3456789.12", "3 456 789,12 ₽"),
        ("999", "999 ₽"),
        ("2000000000", "2 млрд ₽"),
    ],
)
def test_money_in_words(amount: str, text: str) -> None:
    assert texts.money(Money.of(amount)) == text


def test_other_wording() -> None:
    assert texts.rate(Decimal("23.50")) == "23,5%" and texts.rate(Decimal("12")) == "12%"
    assert texts.from_months(12) == "от 12 месяцев"
    assert texts.from_months(1) == "от 1 месяца" and texts.from_months(21) == "от 21 месяца"
    assert texts.legal_forms({"JSC", "LLC"}) == "ООО и АО"
    assert texts.legal_forms({"IE", "JSC", "LLC"}) == "ООО, ИП и АО"
