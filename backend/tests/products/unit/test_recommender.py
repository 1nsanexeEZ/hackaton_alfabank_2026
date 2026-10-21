from seed.products import catalog
from src.core.domain import Money
from src.products.domain.recommender import ProductRecommender, Recommendation
from src.products.domain.value_objects import BorrowerProfile, LoanNeed
from tests.products.factories import borrower


def recommend(
    purpose: str, amount: int, term: int, profile: BorrowerProfile | None = None
) -> list[Recommendation]:
    return ProductRecommender().recommend(
        catalog(), LoanNeed(purpose, Money.of(amount), term), profile
    )


def codes(items: list[Recommendation]) -> list[str]:
    return [r.product.code.value for r in items]


def reason(item: Recommendation, code: str) -> tuple[bool, str]:
    found = [(r.passed, r.message) for r in item.reasons if r.code == code]
    assert len(found) == 1, (code, item.reasons)
    return found[0]


def test_ivanov_unavailable_products_go_last_with_reasons() -> None:
    items = recommend("working_capital", 3_000_000, 24, borrower("ivanov"))
    assert codes(items) == ["UNSECURED", "GOV_SUPPORT", "SECURED", "CREDIT_LINE"]
    assert [r.rank for r in items] == [1, 2, 3, 4]
    assert [r.status for r in items] == ["available"] + ["unavailable"] * 3
    for item in items[1:]:
        assert reason(item, "business_age") == (False, "Нужно от 12 месяцев работы, у вас 8")
    # State support fits the industry: the bank sees that only the age stands in the way.
    passed, message = reason(items[1], "okved")
    assert passed and "ОКВЭД 62 входит в программу господдержки" in message


def test_cash_gap_purpose_for_ivanov_leads_to_the_overdraft() -> None:
    items = recommend("cash_gap", 1_000_000, 6, borrower("ivanov"))
    assert codes(items) == ["OVERDRAFT", "CREDIT_LINE"]
    assert items[0].status == "available" and items[1].status == "unavailable"
    assert reason(items[0], "cash_gap")[0]


def test_cash_gap_forecast_lifts_the_credit_line_and_brings_the_overdraft() -> None:
    plain = recommend("working_capital", 3_000_000, 24, borrower("romashka"))
    assert codes(plain) == ["GOV_SUPPORT", "SECURED", "CREDIT_LINE", "UNSECURED"]

    gap = recommend("working_capital", 3_000_000, 24, borrower("romashka", cash_gap_expected=True))
    assert codes(gap) == ["CREDIT_LINE", "GOV_SUPPORT", "SECURED", "UNSECURED", "OVERDRAFT"]
    passed, message = reason(gap[0], "cash_gap")
    assert passed and message.startswith("По движению денег прогнозируется кассовый разрыв")
    # The overdraft is offered for the cash gap, but 24 months is beyond its term.
    overdraft = gap[-1]
    assert overdraft.status == "needs_adjustment"
    assert reason(overdraft, "cash_gap")[0]
    assert overdraft.adjustments == (
        "Срок от 3 до 12 мес., а запрошено 24 мес. — выберите срок в этих рамках "
        "или «Кредитная линия» (от 12 до 36 мес.)",
    )


def test_no_forecast_no_lift() -> None:
    unknown = recommend("working_capital", 3_000_000, 24, borrower("romashka"))
    no_gap = recommend(
        "working_capital", 3_000_000, 24, borrower("romashka", cash_gap_expected=False)
    )
    assert codes(unknown) == codes(no_gap)
    assert "OVERDRAFT" not in codes(no_gap)


def test_amount_above_the_maximum_suggests_an_adjustment() -> None:
    items = recommend("working_capital", 40_000_000, 24)
    assert codes(items) == ["GOV_SUPPORT", "SECURED", "CREDIT_LINE", "UNSECURED"]
    unsecured = items[-1]
    assert unsecured.status == "needs_adjustment" and not unsecured.fits
    assert unsecured.adjustments == (
        "Максимум 30 млн ₽ — запросите 30 млн ₽ или выберите «Кредит с господдержкой» "
        "(до 100 млн ₽)",
    )
    assert reason(unsecured, "amount")[0] is False
    # The payment is estimated for what the product allows.
    assert unsecured.amount == Money.of(30_000_000) and unsecured.term_months == 24


def test_amount_below_the_minimum() -> None:
    items = recommend("refinancing", 500_000, 24)
    assert codes(items) == ["SECURED", "UNSECURED", "REFINANCE"]
    refinance = items[-1]
    assert refinance.adjustments == (
        "Минимум 1 млн ₽ — запросите от 1 млн ₽ или выберите «Кредит под залог» (от 500 тыс. ₽)",
    )


def test_alternatives_are_only_products_the_borrower_can_get() -> None:
    items = recommend("working_capital", 40_000_000, 24, borrower("ivanov"))
    unsecured = next(r for r in items if r.product.code.value == "UNSECURED")
    assert unsecured.adjustments == ("Максимум 30 млн ₽ — запросите 30 млн ₽",)


def test_without_a_company_eligibility_is_unknown() -> None:
    items = recommend("cash_gap", 1_000_000, 12)
    assert codes(items) == ["CREDIT_LINE", "OVERDRAFT"]
    assert all(r.eligible is None and r.eligibility is None for r in items)
    assert all(r.status == "available" for r in items)
    assert not any(r.code == "business_age" for item in items for r in item.reasons)
    assert all(reason(r, "cash_gap")[0] for r in items)


def test_only_products_for_the_purpose() -> None:
    assert codes(recommend("vehicles", 3_000_000, 36)) == ["AUTO"]
    assert codes(recommend("real_estate", 30_000_000, 120)) == ["MORTGAGE"]
    assert codes(recommend("contract_execution", 5_000_000, 12)) == ["CREDIT_LINE", "UNSECURED"]


def test_reasons_tell_the_route_and_rate() -> None:
    items = recommend("real_estate", 30_000_000, 120, borrower("romashka"))
    mortgage = items[0]
    assert reason(mortgage, "decision") == (
        True,
        "Заявку всегда рассматривает андеррайтер — автоматического решения нет",
    )
    assert reason(mortgage, "collateral") == (True, "Нужен залог: недвижимость")
    assert reason(mortgage, "rate") == (True, "Ставка от 23% до 28% годовых")

    gov = recommend("equipment", 20_000_000, 36, borrower("romashka"))[0]
    assert gov.product.code.value == "GOV_SUPPORT"
    assert reason(gov, "rate") == (
        True,
        "Ставка от 12% до 15% годовых — потолок по программе господдержки",
    )
    assert reason(gov, "decision") == (
        True,
        "Сумма больше 10 млн ₽ — заявку рассмотрит андеррайтер",
    )


def test_payment_range_from_base_to_maximum_rate() -> None:
    for item in recommend("working_capital", 3_000_000, 24, borrower("romashka")):
        assert item.monthly_payment_from <= item.monthly_payment_to
    unsecured = next(
        r
        for r in recommend("working_capital", 3_000_000, 24)
        if r.product.code.value == "UNSECURED"
    )
    # 3 mln for 24 months: 23.5 % and 30 %
    assert unsecured.monthly_payment_from == Money("157865.62")
    assert unsecured.monthly_payment_to == Money("167738.46")
    assert unsecured.repayment == "annuity"


def test_archived_products_are_not_offered() -> None:
    products = catalog()
    next(p for p in products if p.code.value == "OVERDRAFT").archive()
    items = ProductRecommender().recommend(products, LoanNeed("cash_gap", Money.of(1_000_000), 12))
    assert codes(items) == ["CREDIT_LINE"]


def test_matching_is_deterministic() -> None:
    first = recommend("working_capital", 7_000_000, 36, borrower("vector", cash_gap_expected=True))
    second = recommend("working_capital", 7_000_000, 36, borrower("vector", cash_gap_expected=True))
    assert [(codes([r]), r.reasons, r.adjustments) for r in first] == [
        (codes([r]), r.reasons, r.adjustments) for r in second
    ]
