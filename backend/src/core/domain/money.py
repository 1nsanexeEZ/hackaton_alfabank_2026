from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

_KOPECK = Decimal("0.01")


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_KOPECK, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, order=False)
class Money:
    """Amount with currency. Always Decimal, always rounded to kopecks."""

    amount: Decimal
    currency: str = "RUB"

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("Money does not accept float, use Decimal or str")
        object.__setattr__(self, "amount", _quantize(Decimal(self.amount)))
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError(f"Invalid currency code: {self.currency!r}")

    @classmethod
    def of(cls, amount: Decimal | int | str, currency: str = "RUB") -> Self:
        return cls(Decimal(amount), currency)

    @classmethod
    def zero(cls, currency: str = "RUB") -> Self:
        return cls(Decimal(0), currency)

    def _same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError(f"Expected Money, got {type(other).__name__}")
        if other.currency != self.currency:
            raise ValueError(f"Currency mismatch: {self.currency} and {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int) -> "Money":
        if isinstance(factor, float):
            raise TypeError("Money multiplication does not accept float")
        return Money(self.amount * Decimal(factor), self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._same_currency(other)
        return self.amount >= other.amount

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
