"""Table rows <-> domain records. Column names repeat the record fields, so
values are copied by name."""

from dataclasses import fields
from datetime import UTC, datetime
from typing import Any


def aware(value: Any) -> Any:
    """SQLite gives timestamps back without a zone; everything is stored in UTC."""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _stored(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, tuple):
        return list(value)
    return value


def to_record[R](record_type: type[R], row: Any) -> R:
    values = {f.name: aware(getattr(row, f.name)) for f in fields(record_type)}  # type: ignore[arg-type]
    if "routing_reasons" in values:
        values["routing_reasons"] = tuple(values["routing_reasons"] or ())
    return record_type(**values)


def copy_to_row(record: Any, row: Any) -> None:
    for f in fields(record):
        setattr(row, f.name, _stored(getattr(record, f.name)))
