"""Numbers and dates in Russian text, for comparing an answer with its facts.

«1 300 000 ₽», «1,3 млн», «1.3 млн рублей» and «1300000» are one number;
«27%» and «27,00 %» too. Dates are compared as written: dd.mm.yyyy.
"""

import re
from decimal import Decimal, InvalidOperation

_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")
_NUMBER = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,](\d+))?"
    r"(?:\s*(млрд|млн|миллион\w*|тыс\w*))?",
    re.IGNORECASE,
)
_SCALE = {"млрд": 1_000_000_000, "млн": 1_000_000, "миллион": 1_000_000, "тыс": 1_000}


def extract_dates(text: str) -> set[str]:
    return {_normalize_date(d) for d in _DATE.findall(text)}


def _normalize_date(raw: str) -> str:
    d, m, y = raw.split(".")
    return f"{int(d):02d}.{int(m):02d}.{y}"


def extract_numbers(text: str) -> set[Decimal]:
    """Every number in the text, with «млн»/«тыс» applied; dates are skipped."""
    without_dates = _DATE.sub(" ", text)
    found: set[Decimal] = set()
    for match in _NUMBER.finditer(without_dates):
        value = _value(match)
        if value is not None:
            found.add(value)
    return found


def numbers_with_context(text: str) -> list[tuple[Decimal, str]]:
    """Numbers and the few characters after each: tells «3 шага» from «3 ₽»."""
    without_dates = _DATE.sub(" ", text)
    result: list[tuple[Decimal, str]] = []
    for match in _NUMBER.finditer(without_dates):
        value = _value(match)
        if value is not None:
            result.append((value, without_dates[match.end() : match.end() + 12]))
    return result


def _value(match: re.Match[str]) -> Decimal | None:
    whole, fraction, scale = match.group(1), match.group(2), match.group(3)
    raw = re.sub(r"[   ]", "", whole) + (f".{fraction}" if fraction else "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if scale:
        key = next(k for k in _SCALE if scale.lower().startswith(k))
        value *= _SCALE[key]
    return value.normalize()
