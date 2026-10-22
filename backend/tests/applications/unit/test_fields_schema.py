from decimal import Decimal
from typing import Any

import pytest

from src.modules.applications.domain.fields_schema import ProductFieldsSchema

# Shapes the product catalog uses (agent docs: AUTO, MORTGAGE, REFINANCE).
AUTO = {
    "type": "object",
    "properties": {
        "vehicle_type": {"type": "string", "enum": ["car", "truck", "special"]},
        "vehicle_description": {"type": "string", "maxLength": 300},
        "supplier_name": {"type": "string"},
        "price": {"type": "number", "minimum": 1},
    },
    "required": ["vehicle_type", "price"],
}
MORTGAGE = {
    "type": "object",
    "properties": {
        "property_address": {"type": "string", "minLength": 5},
        "property_type": {"type": "string", "enum": ["office", "retail", "warehouse"]},
        "price": {"type": "number", "minimum": 1},
        "cadastral_number": {"type": "string", "pattern": r"\d{2}:\d{2}:\d{6,7}:\d+"},
        "deal_date": {"type": "string", "format": "date"},
    },
    "required": ["property_address", "property_type", "price"],
}
REFINANCE = {
    "type": "object",
    "properties": {
        "loans": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "creditor": {"type": "string"},
                    "outstanding": {"type": "number", "minimum": 0},
                    "monthly_payment": {"type": "number", "minimum": 0},
                    "rate": {"type": "number", "minimum": 0, "maximum": 100},
                    "months_left": {"type": "integer", "minimum": 1},
                },
                "required": ["creditor", "outstanding", "monthly_payment"],
            },
        }
    },
    "required": ["loans"],
}


def errors(
    schema: dict[str, Any], values: dict[str, Any], partial: bool = False
) -> set[tuple[str, str]]:
    return {(e.path, e.code) for e in ProductFieldsSchema(schema).validate(values, partial=partial)}


def test_empty_schema_accepts_nothing_but_nothing() -> None:
    schema = ProductFieldsSchema()
    assert schema.validate({}) == []
    assert {(e.path, e.code) for e in schema.validate({"x": 1})} == {("x", "unknown")}
    assert schema.field_names == ()


def test_valid_values() -> None:
    assert errors(AUTO, {"vehicle_type": "truck", "price": Decimal("4500000.50")}) == set()
    assert (
        errors(
            MORTGAGE,
            {
                "property_address": "Москва, ул. Ленина, 1",
                "property_type": "office",
                "price": 30_000_000,
                "cadastral_number": "77:01:0001001:123",
                "deal_date": "2026-11-01",
            },
        )
        == set()
    )
    assert (
        errors(
            REFINANCE,
            {"loans": [{"creditor": "Банк", "outstanding": 1_000_000, "monthly_payment": 50_000}]},
        )
        == set()
    )


def test_required_and_unknown() -> None:
    assert errors(AUTO, {"color": "red", "vehicle_type": ""}) == {
        ("color", "unknown"),
        ("vehicle_type", "required"),
        ("price", "required"),
    }


def test_partial_skips_required_but_checks_values() -> None:
    assert errors(AUTO, {}, partial=True) == set()
    assert errors(AUTO, {"vehicle_type": "plane"}, partial=True) == {
        ("vehicle_type", "not_allowed")
    }


@pytest.mark.parametrize(
    "values,expected",
    [
        ({"price": "1000"}, ("price", "not_number")),
        ({"price": True}, ("price", "not_number")),
        ({"price": 0}, ("price", "too_small")),
        ({"vehicle_type": 1}, ("vehicle_type", "not_string")),
        ({"vehicle_description": "x" * 301}, ("vehicle_description", "too_long")),
        ({"supplier_name": "x" * 2001}, ("supplier_name", "too_long")),
    ],
)
def test_value_types(values: dict[str, Any], expected: tuple[str, str]) -> None:
    assert expected in errors(AUTO, values, partial=True)


def test_string_formats() -> None:
    bad = {"cadastral_number": "77-01", "deal_date": "01.11.2026", "property_address": "abc"}
    assert errors(MORTGAGE, bad, partial=True) == {
        ("cadastral_number", "bad_format"),
        ("deal_date", "bad_date"),
        ("property_address", "too_short"),
    }


def test_nested_arrays() -> None:
    assert errors(REFINANCE, {"loans": []}) == {("loans", "required")}
    assert errors(REFINANCE, {"loans": "many"}) == {("loans", "not_array")}
    too_many = {"loans": [{"creditor": "x", "outstanding": 1, "monthly_payment": 1}] * 6}
    assert errors(REFINANCE, too_many) == {("loans", "too_many_items")}
    assert errors(
        REFINANCE,
        {"loans": [{"creditor": "Банк", "outstanding": -1, "months_left": 1.5}]},
    ) == {
        ("loans[0].outstanding", "too_small"),
        ("loans[0].months_left", "not_integer"),
        ("loans[0].monthly_payment", "required"),
    }
    assert errors(REFINANCE, {"loans": ["text"]}) == {("loans[0]", "not_object")}
