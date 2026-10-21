"""Domain products and borrowers for products tests."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

from seed.products import catalog
from src.core.domain import Money
from src.products.application.borrowers import borrower_profile
from src.products.domain.product import CreditProduct, ProductStatus
from src.products.domain.value_objects import (
    LEGAL_FORMS,
    AmountRange,
    BorrowerProfile,
    Eligibility,
    ProcessingProfile,
    ProductCode,
    RateRange,
    SecurityRequirement,
    TermRange,
)
from tests.fakes import builders

DEMO_COMPANIES = ("romashka", "ivanov", "vector", "zakat", "progress", "sboy")


def product(**overrides: Any) -> CreditProduct:
    values: dict[str, Any] = {
        "code": ProductCode("TEST"),
        "version": 1,
        "status": ProductStatus.ACTIVE,
        "name": "Тестовый кредит",
        "short_description": "Для тестов",
        "description_plain": "Для тестов",
        "frontend_id": "test",
        "purposes": frozenset({"working_capital"}),
        "facility": "term_loan",
        "repayment_options": ("annuity", "differentiated"),
        "amount": AmountRange(Money.of(100_000), Money.of(5_000_000)),
        "term": TermRange(3, 36),
        "rate": RateRange(Decimal("20"), Decimal("25")),
        "security": SecurityRequirement(),
        "eligibility": Eligibility(6, frozenset(LEGAL_FORMS), Money.of(1_000_000)),
        "processing": ProcessingProfile("standard_v1", Money.of(3_000_000)),
    }
    values.update(overrides)
    return CreditProduct(**values)


def catalog_product(code: str) -> CreditProduct:
    """A fresh copy from the seed catalog (tests may change its status)."""
    return next(p for p in catalog() if p.code.value == code)


def borrower(company: str = "romashka", **overrides: Any) -> BorrowerProfile:
    """Borrower of a demo company (seed/demo_data.py)."""
    return replace(borrower_profile(builders.organization_snapshot(company)), **overrides)
