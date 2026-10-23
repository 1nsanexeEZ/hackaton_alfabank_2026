"""Conditions on gateway flows: a tiny expression language, parsed once when
the route is loaded and evaluated against the process context. No eval():
a route file is data, it must not be able to run code.

    outcome == "APPROVE"
    risk_grade in ["D", "E"] or cash_gap_flag == true
    not complete and info_requests_count < 2

Fields are names from the process context only; literals: strings in double
quotes, numbers, true / false / null, lists in brackets.
"""

import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from src.modules.process.domain.exceptions import ConditionError

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<string>"(?:[^"\\]|\\.)*")
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<op>==|!=|<=|>=|<|>|\(|\)|\[|\]|,)
      | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    )""",
    re.VERBOSE,
)
# Inside a string only \" and \\ are escapes.
_UNESCAPE = re.compile(r"\\(.)")
_KEYWORDS = {"and", "or", "not", "in", "true", "false", "null"}
_COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    position: int


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    position = 0
    while position < len(source):
        if source[position:].strip() == "":
            break
        match = _TOKEN.match(source, position)
        if match is None or match.end() == position:
            raise ConditionError(f"Unexpected character at {position}: {source[position:]!r}")
        kind = match.lastgroup
        assert kind is not None
        value = match.group(kind)
        start = match.start(kind)
        if kind == "name" and value in _KEYWORDS:
            kind = "keyword"
        tokens.append(_Token(kind, value, start))
        position = match.end()
    return tokens


Node = Callable[[Mapping[str, Any]], Any]


class Condition:
    """A compiled condition; `fields` — context names it reads."""

    def __init__(self, source: str, allowed_fields: Collection[str]) -> None:
        self.source = source
        self.fields: set[str] = set()
        self._allowed = set(allowed_fields)
        self._tokens = _tokenize(source)
        self._index = 0
        if not self._tokens:
            raise ConditionError("Empty condition")
        self._root = self._or()
        if self._index != len(self._tokens):
            token = self._tokens[self._index]
            raise ConditionError(f"Unexpected {token.value!r} at {token.position}")

    def __call__(self, context: Mapping[str, Any]) -> bool:
        return bool(self._root(context))

    def __repr__(self) -> str:
        return f"Condition({self.source!r})"

    # --- recursive descent ----------------------------------------------------

    def _peek(self) -> _Token | None:
        return self._tokens[self._index] if self._index < len(self._tokens) else None

    def _take(self, value: str | None = None) -> _Token:
        token = self._peek()
        if token is None:
            raise ConditionError(f"Unexpected end of condition {self.source!r}")
        if value is not None and token.value != value:
            raise ConditionError(f"Expected {value!r} at {token.position}, got {token.value!r}")
        self._index += 1
        return token

    def _accept(self, value: str) -> bool:
        token = self._peek()
        if token is not None and token.value == value and token.kind in ("keyword", "op"):
            self._index += 1
            return True
        return False

    def _or(self) -> Node:
        left = self._and()
        while self._accept("or"):
            right = self._and()
            left = (lambda a, b: lambda ctx: a(ctx) or b(ctx))(left, right)
        return left

    def _and(self) -> Node:
        left = self._not()
        while self._accept("and"):
            right = self._not()
            left = (lambda a, b: lambda ctx: a(ctx) and b(ctx))(left, right)
        return left

    def _not(self) -> Node:
        if self._accept("not"):
            inner = self._not()
            return lambda ctx: not inner(ctx)
        return self._comparison()

    def _comparison(self) -> Node:
        left = self._operand()
        token = self._peek()
        if token is not None and token.kind == "op" and token.value in _COMPARISONS:
            self._index += 1
            right = self._operand()
            return _compare(token.value, left, right)
        if self._accept("in"):
            items = self._list()
            return lambda ctx: left(ctx) in [item(ctx) for item in items]
        if self._accept("not"):
            self._take("in")
            items = self._list()
            return lambda ctx: left(ctx) not in [item(ctx) for item in items]
        return left

    def _list(self) -> list[Node]:
        self._take("[")
        items = [self._operand()]
        while self._accept(","):
            items.append(self._operand())
        self._take("]")
        return items

    def _operand(self) -> Node:
        if self._accept("("):
            inner = self._or()
            self._take(")")
            return inner
        token = self._take()
        if token.kind == "string":
            text = _UNESCAPE.sub(lambda m: m.group(1), token.value[1:-1])
            return lambda ctx: text
        if token.kind == "number":
            number = Decimal(token.value)
            return lambda ctx: number
        if token.kind == "keyword" and token.value in ("true", "false", "null"):
            literal = {"true": True, "false": False, "null": None}[token.value]
            return lambda ctx: literal
        if token.kind == "name":
            name = token.value
            if name not in self._allowed:
                raise ConditionError(f"Unknown field {name!r} at {token.position}")
            self.fields.add(name)
            return lambda ctx: ctx.get(name)
        raise ConditionError(f"Unexpected {token.value!r} at {token.position}")


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _compare(op: str, left: Node, right: Node) -> Node:
    def evaluate(ctx: Mapping[str, Any]) -> bool:
        a, b = left(ctx), right(ctx)
        if op in ("==", "!="):
            na, nb = _number(a), _number(b)
            equal = na == nb if na is not None and nb is not None else a == b
            return equal if op == "==" else not equal
        na, nb = _number(a), _number(b)
        if na is None or nb is None:
            return False  # ordering with a missing value is never true
        return {"<": na < nb, "<=": na <= nb, ">": na > nb, ">=": na >= nb}[op]

    return evaluate
