"""Validation of the extra form fields a product asks for (`application_fields_schema`).

Products describe the fields with a JSON Schema subset; this is a small
dependency-free validator for exactly that subset:

    type: object (properties, required, additionalProperties: false by default),
          array (items, minItems, maxItems), string (minLength, maxLength, pattern,
          enum, format: date), integer / number (minimum, maximum, enum), boolean
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

# Safety net for strings without maxLength: form data, not documents.
MAX_STRING_LENGTH = 2000
MAX_ARRAY_ITEMS = 100


@dataclass(frozen=True, slots=True)
class FieldError:
    path: str
    code: str


class ProductFieldsSchema:
    def __init__(self, schema: Mapping[str, Any] | None = None) -> None:
        self._schema: Mapping[str, Any] = schema or {"type": "object", "properties": {}}

    @property
    def raw(self) -> Mapping[str, Any]:
        return self._schema

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(self._schema.get("properties", {}))

    @property
    def required_names(self) -> tuple[str, ...]:
        return tuple(self._schema.get("required", ()))

    def validate(self, values: Mapping[str, Any], *, partial: bool = False) -> list[FieldError]:
        """`partial` — a draft being saved: check what is filled, skip `required`."""
        return _validate_object(self._schema, values, "", partial)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _validate(schema: Mapping[str, Any], value: Any, path: str, partial: bool) -> list[FieldError]:
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, Mapping):
            return [FieldError(path, "not_object")]
        return _validate_object(schema, value, path, partial)
    if kind == "array":
        return _validate_array(schema, value, path, partial)
    if kind == "string":
        return _validate_string(schema, value, path)
    if kind in ("integer", "number"):
        return _validate_number(schema, value, path, integer=kind == "integer")
    if kind == "boolean":
        return [] if isinstance(value, bool) else [FieldError(path, "not_boolean")]
    return [FieldError(path, "unsupported_schema")]


def _validate_object(
    schema: Mapping[str, Any], values: Mapping[str, Any], path: str, partial: bool
) -> list[FieldError]:
    properties: Mapping[str, Any] = schema.get("properties", {})
    errors: list[FieldError] = []
    if not schema.get("additionalProperties", False):
        errors += [
            FieldError(_join(path, key), "unknown") for key in values if key not in properties
        ]
    if not partial:
        errors += [
            FieldError(_join(path, name), "required")
            for name in schema.get("required", ())
            if _is_empty(values.get(name))
        ]
    for name, field_schema in properties.items():
        value = values.get(name)
        if not _is_empty(value):
            errors += _validate(field_schema, value, _join(path, name), partial)
    return errors


def _validate_array(
    schema: Mapping[str, Any], value: Any, path: str, partial: bool
) -> list[FieldError]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return [FieldError(path, "not_array")]
    if len(value) > schema.get("maxItems", MAX_ARRAY_ITEMS):
        return [FieldError(path, "too_many_items")]
    if not partial and len(value) < schema.get("minItems", 0):
        return [FieldError(path, "too_few_items")]
    items = schema.get("items")
    if items is None:
        return []
    errors: list[FieldError] = []
    for index, item in enumerate(value):
        errors += _validate(items, item, f"{path}[{index}]", partial)
    return errors


def _validate_string(schema: Mapping[str, Any], value: Any, path: str) -> list[FieldError]:
    if not isinstance(value, str):
        return [FieldError(path, "not_string")]
    if len(value) > schema.get("maxLength", MAX_STRING_LENGTH):
        return [FieldError(path, "too_long")]
    if len(value) < schema.get("minLength", 0):
        return [FieldError(path, "too_short")]
    if "enum" in schema and value not in schema["enum"]:
        return [FieldError(path, "not_allowed")]
    if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
        return [FieldError(path, "bad_format")]
    if schema.get("format") == "date":
        try:
            date.fromisoformat(value)
        except ValueError:
            return [FieldError(path, "bad_date")]
    return []


def _validate_number(
    schema: Mapping[str, Any], value: Any, path: str, *, integer: bool
) -> list[FieldError]:
    if isinstance(value, bool):
        return [FieldError(path, "not_number")]
    if integer and not isinstance(value, int):
        return [FieldError(path, "not_integer")]
    if not isinstance(value, int | float | Decimal):
        return [FieldError(path, "not_number")]
    number = Decimal(str(value))
    if "minimum" in schema and number < Decimal(str(schema["minimum"])):
        return [FieldError(path, "too_small")]
    if "maximum" in schema and number > Decimal(str(schema["maximum"])):
        return [FieldError(path, "too_large")]
    if "enum" in schema and value not in schema["enum"]:
        return [FieldError(path, "not_allowed")]
    return []


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name
