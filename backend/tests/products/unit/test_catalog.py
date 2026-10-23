"""The seed catalog agrees with the contract and with what applications accept."""

from typing import get_args

import pytest

from seed.demo_data import PRODUCT_CODES
from seed.products import catalog
from src.modules.applications.domain.fields_schema import ProductFieldsSchema
from src.modules.applications.domain.value_objects import COLLATERAL_TYPES
from src.modules.applications.domain.value_objects import PURPOSES as APPLICATION_PURPOSES
from src.modules.products.domain.value_objects import PURPOSES
from src.modules.products.facade import Purpose

FRONTEND_IDS = {
    "UNSECURED": "unsecured",
    "SECURED": "secured",
    "CREDIT_LINE": "credit-line",
    "OVERDRAFT": "overdraft",
    "AUTO": "auto",
    "MORTGAGE": "mortgage",
    "REFINANCE": "refinance",
    "GOV_SUPPORT": "gov-support",
    "STARTUP": "startup",
}


def test_codes_order_and_frontend_ids() -> None:
    products = catalog()
    assert tuple(p.code.value for p in products) == PRODUCT_CODES
    assert {p.code.value: p.frontend_id for p in products} == FRONTEND_IDS
    assert [p.sort_order for p in products] == sorted(p.sort_order for p in products)
    assert all(p.is_selectable and p.version == 1 for p in products)


def test_every_purpose_of_an_application_has_a_product() -> None:
    assert set(PURPOSES) == set(get_args(Purpose)) == APPLICATION_PURPOSES
    covered = set().union(*(p.purposes for p in catalog()))
    assert covered == set(PURPOSES)


def test_collateral_types_are_the_ones_an_application_declares() -> None:
    for product in catalog():
        assert set(product.security.collateral_types) <= COLLATERAL_TYPES, product.code


def test_secured_kinds_need_collateral() -> None:
    required = {p.code.value for p in catalog() if p.security.collateral == "required"}
    assert required == {"SECURED", "AUTO", "MORTGAGE"}


@pytest.mark.parametrize(
    "code,values",
    [
        (
            "AUTO",
            {
                "vehicle_type": "truck",
                "vehicle_description": "ГАЗель Next, 2025",
                "supplier_name": "ООО «Автоторг»",
                "price": 3_500_000,
            },
        ),
        (
            "MORTGAGE",
            {"property_address": "Москва, ул. Тверская, 1", "property_type": "office", "price": 1},
        ),
        (
            "REFINANCE",
            {
                "loans": [
                    {
                        "creditor": "Банк",
                        "outstanding": 2_000_000,
                        "monthly_payment": 95_000,
                        "rate": 26.5,
                    }
                ]
            },
        ),
    ],
)
def test_fields_schema_is_understood_by_applications(code: str, values: dict) -> None:
    product = next(p for p in catalog() if p.code.value == code)
    schema = ProductFieldsSchema(product.application_fields_schema)
    assert schema.validate(values) == []
    missing = {e.path for e in schema.validate({})}
    assert missing == {f"{name}" for name in schema.required_names}


def test_other_products_ask_no_extra_fields() -> None:
    plain = {p.code.value for p in catalog() if not p.application_fields_schema}
    assert plain == {"UNSECURED", "SECURED", "CREDIT_LINE", "OVERDRAFT", "GOV_SUPPORT", "STARTUP"}


def test_startup_is_only_for_a_company_without_turnover_and_never_automatic() -> None:
    startup = next(p for p in catalog() if p.code.value == "STARTUP")
    assert startup.eligibility.startup_only and startup.eligibility.min_business_age_months == 0
    assert [d.type for d in startup.required_documents] == ["business_plan", "financial_model"]
    assert startup.processing.workflow_code == "startup_v2"
    assert startup.processing.auto_decision_limit.is_zero
    assert startup.support_program is not None
    assert not any(p.eligibility.startup_only for p in catalog() if p.code.value != "STARTUP")


def test_mortgage_is_for_companies_only_and_never_automatic() -> None:
    mortgage = next(p for p in catalog() if p.code.value == "MORTGAGE")
    assert mortgage.eligibility.allowed_legal_forms == {"LLC", "JSC"}
    assert mortgage.processing.auto_decision_limit.is_zero
