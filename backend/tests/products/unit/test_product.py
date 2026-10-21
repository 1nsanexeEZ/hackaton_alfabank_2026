from decimal import Decimal

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import InvalidStatusTransitionError, ValidationError
from src.products.domain.errors import ProductNotAvailableError
from src.products.domain.product import ProductStatus
from src.products.domain.value_objects import (
    AmountRange,
    DocumentRequirement,
    ProcessingProfile,
    RateRange,
    SecurityRequirement,
    SupportProgram,
)
from tests.products.factories import catalog_product, product


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"purposes": frozenset()}, "purposes"),
        ({"purposes": frozenset({"yacht"})}, "purposes"),
        ({"facility": "leasing"}, "facility"),
        ({"repayment_options": ()}, "repayment_options"),
        ({"repayment_options": ("balloon",)}, "repayment_options"),
        ({"repayment_options": ("annuity", "annuity")}, "repayment_options"),
        ({"version": 0}, "version"),
        ({"name": "  "}, "name"),
        ({"frontend_id": "Credit Line"}, "frontend_id"),
        (
            {"processing": ProcessingProfile("standard_v1", Money.of(5_000_001))},
            "auto_decision_limit",
        ),
        (
            {
                "security": SecurityRequirement(
                    "optional", ("real_estate",), required_from=Money.of(10_000_000)
                )
            },
            "collateral_required_from",
        ),
        (
            {"support_program": SupportProgram("P", "Программа", Decimal("26"))},
            "support_program.rate_cap",
        ),
        (
            {
                "required_documents": (
                    DocumentRequirement("bank_statement", "Выписка"),
                    DocumentRequirement("bank_statement", "Ещё выписка"),
                )
            },
            "required_documents",
        ),
        ({"application_fields_schema": {"type": "array"}}, "application_fields_schema"),
    ],
)
def test_invariants(overrides: dict, field: str) -> None:
    with pytest.raises(ValidationError) as error:
        product(**overrides)
    assert error.value.details is not None and error.value.details["field"] == field


def test_auto_decision_limit_may_equal_the_maximum() -> None:
    assert product(processing=ProcessingProfile("standard_v1", Money.of(5_000_000)))


def test_archived_product_can_not_be_chosen() -> None:
    loan = product()
    assert loan.is_selectable
    loan.archive()
    assert loan.status == ProductStatus.ARCHIVED and not loan.is_selectable
    with pytest.raises(ProductNotAvailableError) as error:
        loan.snapshot()
    assert error.value.status_code == 409
    assert error.value.details == {"code": "TEST", "status": "archived"}
    with pytest.raises(InvalidStatusTransitionError):
        loan.archive()
    with pytest.raises(InvalidStatusTransitionError):
        loan.activate()


def test_draft_is_activated_once() -> None:
    loan = product(status="draft")
    assert not loan.is_selectable
    loan.activate()
    assert loan.is_selectable
    with pytest.raises(InvalidStatusTransitionError):
        loan.activate()


def test_fits_amount_and_term() -> None:
    loan = product()
    assert loan.fits(Money.of(100_000), 3) and loan.fits(Money.of(5_000_000), 36)
    assert not loan.fits(Money.of(5_000_001), 12)
    assert not loan.fits(Money.of(1_000_000), 48)


def test_unsecured_asks_for_financials_above_five_million() -> None:
    unsecured = catalog_product("UNSECURED")

    def types(amount: int, legal_form: str) -> list[str]:
        return [d.type for d in unsecured.documents_for(Money.of(amount), legal_form)]

    assert types(3_000_000, "LLC") == []
    assert types(4_999_999, "LLC") == []
    assert types(5_000_001, "LLC") == ["financial_report"]
    assert types(10_000_000, "JSC") == ["financial_report"]
    # An individual entrepreneur keeps no accounting statements: a tax return instead.
    assert types(10_000_000, "IE") == ["tax_return"]


def test_documents_without_conditions_are_always_required() -> None:
    secured = catalog_product("SECURED")
    for legal_form, report in (("LLC", "financial_report"), ("IE", "tax_return")):
        documents = [d.type for d in secured.documents_for(Money.of(500_000), legal_form)]
        assert documents == [report, "collateral_documents"]


def test_manual_review_above_the_auto_decision_limit() -> None:
    unsecured = catalog_product("UNSECURED")
    assert not unsecured.requires_manual_review(Money.of(5_000_000))
    assert unsecured.requires_manual_review(Money("5000000.01"))
    # Business mortgage: every application goes to an underwriter.
    assert catalog_product("MORTGAGE").requires_manual_review(Money.of(3_000_000))


def test_collateral_by_amount() -> None:
    line = catalog_product("CREDIT_LINE")
    assert not line.needs_collateral(Money.of(29_000_000))
    assert line.needs_collateral(Money.of(30_000_000))
    assert catalog_product("SECURED").needs_collateral(Money.of(500_000))
    assert not catalog_product("UNSECURED").needs_collateral(Money.of(30_000_000))


def test_snapshot_copies_the_terms() -> None:
    secured = catalog_product("SECURED")
    terms = secured.snapshot()
    assert (terms.code, terms.version) == ("SECURED", 1)
    assert terms.amount == secured.amount and terms.term == secured.term
    assert terms.collateral_required and terms.collateral_required_from is None
    assert terms.required_documents == secured.required_documents
    assert terms.workflow_code == "secured_v1"
    assert terms.auto_decision_limit == Money.of(10_000_000)


def test_support_program_caps_the_client_rate() -> None:
    gov = catalog_product("GOV_SUPPORT")
    assert gov.rate == RateRange(Decimal("12"), Decimal("18"))
    assert gov.client_rate == RateRange(Decimal("12"), Decimal("15"))
    assert gov.snapshot().rate.max == Decimal("15")
    assert catalog_product("UNSECURED").client_rate == catalog_product("UNSECURED").rate


def test_default_repayment_is_the_first_option() -> None:
    assert catalog_product("CREDIT_LINE").default_repayment == "interest_only"
    assert product().default_repayment == "annuity"


def test_maximum_below_the_auto_decision_limit_is_rejected() -> None:
    # The factory's auto decision limit is 3 million.
    with pytest.raises(ValidationError):
        product(amount=AmountRange(Money.of(100_000), Money.of(1_000_000)))
