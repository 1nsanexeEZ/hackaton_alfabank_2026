"""Facts: the only things the answer may state.

Code turns DTOs into short Russian lines. The same lines go to the model as
CONTEXT and to the post-check as the list of allowed numbers and dates, so a
number the model invents has nothing to match.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.modules.assistant.domain.numbers import extract_dates, extract_numbers


@dataclass(slots=True)
class Facts:
    lines: list[str] = field(default_factory=list)
    # Text the client typed: shown to the model as quoted data, never as instructions.
    client_text: list[str] = field(default_factory=list)
    outcome: str | None = None

    def add(self, line: str) -> None:
        if line:
            self.lines.append(line)

    def extend(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.add(line)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def allowed_numbers(self) -> set[Decimal]:
        return extract_numbers(self.text)

    def allowed_dates(self) -> set[str]:
        return extract_dates(self.text)


def money(value: Decimal) -> str:
    """1 300 000 ₽, 39 695,93 ₽."""
    value = value.quantize(Decimal("0.01"))
    whole, _, kopecks = f"{value:,.2f}".replace(",", " ").partition(".")
    return f"{whole},{kopecks} ₽" if kopecks != "00" else f"{whole} ₽"


def percent(value: Decimal) -> str:
    """27%, 23,5%."""
    text = f"{value.normalize():f}".replace(".", ",")
    return f"{text}%"


def months(value: int) -> str:
    return f"{value} мес."


def day(value: datetime) -> str:
    return value.strftime("%d.%m.%Y")
