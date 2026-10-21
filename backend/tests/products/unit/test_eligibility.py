"""Eligibility of the six demo companies (seed/demo_data.py) for the seed catalog."""

import pytest

from seed.products import catalog
from src.core.domain import Money
from tests.products.factories import DEMO_COMPANIES, borrower, catalog_product

ALL = {"UNSECURED", "SECURED", "CREDIT_LINE", "OVERDRAFT", "AUTO", "MORTGAGE", "REFINANCE"}
EXPECTED = {
    # 72 months, LLC, 48 mln, OKVED 56 (catering) — everything, state support included.
    "romashka": ALL | {"GOV_SUPPORT"},
    # 8 months, IE, 6 mln, OKVED 62: too young for 12-month products.
    "ivanov": {"UNSECURED", "OVERDRAFT", "AUTO"},
    # 48 months, 30 mln, OKVED 41 (construction) is not a priority industry.
    "vector": ALL,
    # 20 mln is below the mortgage minimum; liquidation does not block here.
    "zakat": ALL - {"MORTGAGE"},
    "progress": ALL,
    "sboy": ALL - {"MORTGAGE"},
}


def reasons_by_code(product_code: str, company: str) -> dict[str, tuple[bool, str]]:
    check = catalog_product(product_code).check_eligibility(borrower(company))
    return {r.code: (r.passed, r.message) for r in check.reasons}


@pytest.mark.parametrize("company", DEMO_COMPANIES)
def test_demo_company_eligibility(company: str) -> None:
    profile = borrower(company)
    eligible = {p.code.value for p in catalog() if p.check_eligibility(profile).eligible}
    assert eligible == EXPECTED[company]


@pytest.mark.parametrize("company", DEMO_COMPANIES)
def test_every_check_explains_itself(company: str) -> None:
    for product in catalog():
        check = product.check_eligibility(borrower(company))
        assert check.reasons and all(r.message for r in check.reasons)
        assert check.eligible == all(r.passed for r in check.reasons)
        assert check.product_code == product.code.value


def test_ivanov_is_too_young_for_the_credit_line() -> None:
    reasons = reasons_by_code("CREDIT_LINE", "ivanov")
    assert reasons["business_age"] == (False, "Нужно от 12 месяцев работы, у вас 8")
    assert reasons["annual_revenue"] == (False, "Нужна выручка от 12 млн ₽ в год, у вас 6 млн ₽")
    assert reasons["legal_form"] == (True, "Форма бизнеса ИП подходит")


def test_ivanov_fits_state_support_by_industry_but_not_by_age() -> None:
    reasons = reasons_by_code("GOV_SUPPORT", "ivanov")
    assert reasons["business_age"] == (False, "Нужно от 12 месяцев работы, у вас 8")
    passed, message = reasons["okved"]
    assert passed and message.startswith("ОКВЭД 62 входит в программу господдержки")
    # The MSP registry is not in the snapshot: checked later, does not block.
    assert reasons["msp_registry"][0] is True
    assert "реестр" in reasons["msp_registry"][1]


def test_ivanov_gets_unsecured_and_overdraft() -> None:
    for code in ("UNSECURED", "OVERDRAFT"):
        assert all(passed for passed, _ in reasons_by_code(code, "ivanov").values())


def test_industry_outside_the_program() -> None:
    passed, message = reasons_by_code("GOV_SUPPORT", "vector")["okved"]
    assert not passed and message.startswith("ОКВЭД 41 не входит")


def test_legal_form_reason_for_an_entrepreneur() -> None:
    passed, message = reasons_by_code("MORTGAGE", "ivanov")["legal_form"]
    assert not passed
    assert message == "Продукт доступен только для ООО и АО, а у вас ИП"


def test_registry_status_and_verification_are_noted_not_blocking() -> None:
    zakat = reasons_by_code("UNSECURED", "zakat")
    assert zakat["registry_status"][0] is True and "ликвидируется" in zakat["registry_status"][1]
    vector = reasons_by_code("UNSECURED", "vector")
    assert vector["verification"][0] is True
    assert "registry_status" not in reasons_by_code("UNSECURED", "romashka")
    assert "verification" not in reasons_by_code("UNSECURED", "romashka")


def test_msp_registry_answer_is_used_when_known() -> None:
    gov = catalog_product("GOV_SUPPORT")
    outside = gov.check_eligibility(borrower("romashka", in_msp_registry=False))
    assert not outside.eligible
    assert [r.code for r in outside.failed] == ["msp_registry"]
    assert gov.check_eligibility(borrower("romashka", in_msp_registry=True)).eligible


def test_unknown_revenue_does_not_pass() -> None:
    check = catalog_product("UNSECURED").check_eligibility(
        borrower("romashka", annual_revenue=None)
    )
    assert [r.code for r in check.failed] == ["annual_revenue"]


def test_revenue_threshold_is_inclusive() -> None:
    profile = borrower("romashka", annual_revenue=Money.of(3_000_000))
    assert catalog_product("UNSECURED").check_eligibility(profile).eligible
