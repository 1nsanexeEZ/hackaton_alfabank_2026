"""Тексты для клиента: каталог `ReasonCode → текст` из `explanations_ru.yaml`.

Принципы: без внутренних цифр модели, порогов и названий правил; говорим, что произошло и что
можно сделать. В шаблонах — только именованные подстановки из `PLACEHOLDERS` (суммы оффера,
срок, месяц разрыва, название продукта); загрузчик проверяет это при старте.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from src.modules.decision.domain.model import ReasonCode

PLACEHOLDERS = frozenset({"amount", "requested_amount", "term", "month", "product", "collateral"})
NOTE_KEYS = frozenset({"cash_gap_no_alternative", "alternative"})
CONDITION_KEYS = frozenset(
    {"collateral", "guarantee_owner", "guarantee_msp_corporation", "target_use", "cash_gap"}
)

# Предложный падеж: «разрыв в ноябре 2026».
_MONTHS_IN = (
    "январе",
    "феврале",
    "марте",
    "апреле",
    "мае",
    "июне",
    "июле",
    "августе",
    "сентябре",
    "октябре",
    "ноябре",
    "декабре",
)


@dataclass(frozen=True, slots=True)
class ReasonText:
    text: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class ExplanationCatalog:
    version: str
    outcomes: Mapping[str, str]
    reasons: Mapping[ReasonCode, ReasonText]
    notes: Mapping[str, str]
    conditions: Mapping[str, str]
    products: Mapping[str, str]  # код продукта → название в тексте («овердрафт»)
    collateral_types: Mapping[str, str]

    def product_name(self, code: str) -> str:
        return self.products.get(code, code)

    def collateral_name(self, kind: str) -> str:
        return self.collateral_types.get(kind, kind)


def render(template: str, values: Mapping[str, str]) -> str:
    return template.format_map({key: values.get(key, "") for key in PLACEHOLDERS})


def month_in(month: str | None) -> str:
    """`2026-11` → «ноябре 2026»; без месяца — «ближайшие месяцы»."""
    if month is None:
        return "ближайшие месяцы"
    year, number = month.split("-", 1)
    return f"{_MONTHS_IN[int(number) - 1]} {year}"


def rub(amount: Decimal) -> str:
    """Сумма для клиента: целые рубли с разрядами, «3 000 000 ₽»."""
    whole = int(amount.quantize(Decimal(1), rounding=ROUND_DOWN))
    return f"{whole:,}".replace(",", " ") + " ₽"
