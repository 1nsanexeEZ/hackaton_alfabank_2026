from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import ValidationError
from src.modules.applications.domain.value_objects import (
    ApplicationNumber,
    CollateralDeclaration,
    DocumentRequirement,
    LoanRequest,
)
from tests.applications.unit.factories import NOW, offer, terms


def test_application_number() -> None:
    assert str(ApplicationNumber.issue(2026, 123)) == "КР-2026-000123"
    for bad in ("KR-2026-000123", "КР-26-000123", "КР-2026-123"):
        with pytest.raises(ValueError):
            ApplicationNumber(bad)
    with pytest.raises(ValueError):
        ApplicationNumber.issue(2026, 1_000_000)


def test_loan_request_may_be_partial_in_a_draft() -> None:
    request = LoanRequest(purpose="equipment")
    assert not request.is_complete
    assert request.missing_fields() == ["request.amount", "request.term_months"]
    assert LoanRequest(Money.of(1), 1, "cash_gap").is_complete


@pytest.mark.parametrize(
    "kwargs,field",
    [
        ({"amount": Money.of(0)}, "request.amount"),
        ({"amount": Money.of(-5)}, "request.amount"),
        ({"term_months": 0}, "request.term_months"),
        ({"purpose": "yacht"}, "request.purpose"),
        ({"purpose_comment": "x" * 501}, "request.purpose_comment"),
    ],
)
def test_loan_request_validation(kwargs: dict, field: str) -> None:
    with pytest.raises(ValidationError) as error:
        LoanRequest(**kwargs)
    assert error.value.details["field"] == field


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": "boat"},
        {"description": "  "},
        {"declared_value": Money.of(0)},
        {"owner": "neighbour"},
    ],
)
def test_collateral_validation(kwargs: dict) -> None:
    values = {
        "type": "equipment",
        "description": "Станок",
        "declared_value": Money.of(1),
        "owner": "self",
    }
    with pytest.raises(ValidationError):
        CollateralDeclaration(**{**values, **kwargs})


def test_document_requirement_conditions() -> None:
    always = DocumentRequirement("bank_statement", "Выписка")
    from_amount = DocumentRequirement("financial_statement", "Отчётность", Money.of(3_000_000))
    for_companies = DocumentRequirement("charter", "Устав", legal_forms=frozenset({"LLC", "JSC"}))

    assert always.applies(None, None)
    assert not from_amount.applies(Money.of(2_999_999), "LLC")
    assert from_amount.applies(Money.of(3_000_000), "LLC")
    assert not from_amount.applies(None, "LLC")
    assert for_companies.applies(None, "JSC") and not for_companies.applies(None, "IE")

    product = terms(required_documents=(always, from_amount, for_companies))
    assert product.documents_for(Money.of(5_000_000), "IE") == [
        "bank_statement",
        "financial_statement",
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": Money.of(0)},
        {"term_months": 0},
        {"rate": Decimal("-1")},
        {"expires_at": datetime(2026, 10, 28)},  # naive
    ],
    ids=["amount", "term", "rate", "naive-expiry"],
)
def test_offer_validation(changes: dict) -> None:
    with pytest.raises(ValueError):
        replace(offer(), **changes)
    assert offer().is_expired(NOW) is False
