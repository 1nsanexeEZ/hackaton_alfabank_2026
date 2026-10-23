"""Russian wording of reasons: amounts, rates, months, titles of codes."""

from collections.abc import Iterable
from decimal import Decimal

from src.core.domain import Money
from src.modules.products.domain.value_objects import LEGAL_FORMS, ordered

PURPOSE_TITLES: dict[str, str] = {
    "working_capital": "пополнение оборотных средств",
    "cash_gap": "покрытие кассового разрыва",
    "equipment": "покупка оборудования",
    "vehicles": "покупка транспорта",
    "real_estate": "покупка недвижимости",
    "contract_execution": "исполнение контракта",
    "refinancing": "рефинансирование кредитов",
    "expansion": "развитие бизнеса",
}
LEGAL_FORM_TITLES: dict[str, str] = {"LLC": "ООО", "IE": "ИП", "JSC": "АО"}
REGISTRY_STATUS_TITLES: dict[str, str] = {
    "active": "действующая",
    "liquidating": "ликвидируется",
    "liquidated": "ликвидирована",
    "bankrupt": "банкротство",
}
COLLATERAL_TYPE_TITLES: dict[str, str] = {
    "real_estate": "недвижимость",
    "equipment": "оборудование",
    "vehicle": "транспорт",
    "goods": "товары в обороте",
}

_UNITS = (
    (Decimal(1_000_000_000), "млрд"),
    (Decimal(1_000_000), "млн"),
    (Decimal(1_000), "тыс."),
)
_CENT = Decimal("0.01")


def number(value: Decimal) -> str:
    """`Decimal("23.50")` -> `23,5`."""
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


def money(value: Money) -> str:
    """Short form when it is exact (`5 млн ₽`, `300 тыс. ₽`, `1,25 млн ₽`),
    otherwise every digit (`3 456 789,12 ₽`)."""
    amount = value.amount
    for divisor, unit in _UNITS:
        if amount >= divisor:
            scaled = amount / divisor
            if scaled == scaled.quantize(_CENT):
                return f"{number(scaled)} {unit} ₽"
            break
    whole, _, fraction = f"{amount:,.2f}".replace(",", " ").partition(".")
    return f"{whole},{fraction} ₽" if fraction != "00" else f"{whole} ₽"


def rate(value: Decimal) -> str:
    return f"{number(value)}%"


def plural(count: int, one: str, few: str, many: str) -> str:
    last, last_two = count % 10, count % 100
    if last == 1 and last_two != 11:
        return one
    if 2 <= last <= 4 and not 12 <= last_two <= 14:
        return few
    return many


def from_months(count: int) -> str:
    """`от 12 месяцев`, `от 1 месяца`."""
    return f"от {count} {plural(count, 'месяца', 'месяцев', 'месяцев')}"


def legal_forms(forms: Iterable[str]) -> str:
    """`ООО, ИП и АО`."""
    titles = [LEGAL_FORM_TITLES.get(form, form) for form in ordered(forms, LEGAL_FORMS)]
    if len(titles) == 1:
        return titles[0]
    return f"{', '.join(titles[:-1])} и {titles[-1]}"


def collateral_types(types: Iterable[str]) -> str:
    titles = [COLLATERAL_TYPE_TITLES.get(t, t) for t in types]
    if len(titles) <= 1:
        return "".join(titles)
    return f"{', '.join(titles[:-1])} или {titles[-1]}"
