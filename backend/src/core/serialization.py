"""Frozen DTO dataclasses <-> JSON-safe values, without losing precision:
Decimal as a string, dates in ISO format, UUID as a string. Used when a
module stores a copy of another module's DTO (snapshots, read models)."""

import dataclasses
import types
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
from uuid import UUID


def to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal | UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        items = [to_jsonable(v) for v in value]
        return sorted(items) if isinstance(value, set | frozenset) else items
    return value


def from_jsonable[T](cls: type[T], data: Any) -> T:
    return _decode(cls, data)  # type: ignore[no-any-return]


def _decode(annotation: Any, data: Any) -> Any:
    if data is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, types.UnionType):
        options = [a for a in args if a is not type(None)]
        return _decode(options[0], data) if len(options) == 1 else data
    if origin is Literal or annotation is Any:
        return data
    if origin is tuple:
        item = args[0] if args else Any
        return tuple(_decode(item, v) for v in data)
    if origin in (list, set, frozenset):
        item = args[0] if args else Any
        return origin(_decode(item, v) for v in data)
    if origin is dict or annotation is dict:
        return dict(data)
    if dataclasses.is_dataclass(annotation):
        hints = get_type_hints(annotation)
        values = {
            f.name: _decode(hints[f.name], data[f.name])
            for f in dataclasses.fields(annotation)
            if f.name in data
        }
        return annotation(**values)
    if annotation is Decimal:
        return Decimal(data)
    if annotation is UUID:
        return UUID(data)
    if annotation is datetime:
        return datetime.fromisoformat(data)
    if annotation is date:
        return date.fromisoformat(data)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(data)
    return data
