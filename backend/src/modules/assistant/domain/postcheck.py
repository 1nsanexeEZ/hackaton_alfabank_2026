"""Post-check of a model answer. Any violation → the template answer instead.

Checks, in order: length, Russian, no internal terms the facts don't have,
no promise of approval, every number and date is in the facts.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from src.modules.assistant.domain.facts import Facts
from src.modules.assistant.domain.numbers import extract_dates, numbers_with_context

MAX_ANSWER_CHARS = 1200
MIN_ANSWER_CHARS = 2

# Never in an answer to a client unless the bank's own client text uses it.
INTERNAL_TERMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("score", re.compile(r"\bскор(?:инг\w*)?\b|\bscor\w*", re.IGNORECASE)),
    ("points", re.compile(r"\bбалл\w*", re.IGNORECASE)),
    ("grade", re.compile(r"грейд|\bgrade\b|рейтинг", re.IGNORECASE)),
    ("bureau", re.compile(r"\bбки\b|бюро\s+кредитн", re.IGNORECASE)),
    ("reason_code", re.compile(r"\b[A-Z]{2,}(?:_[A-Z0-9]+)+\b|reason[_\s]?code", re.IGNORECASE)),
    ("rule_trace", re.compile(r"rule[_\s]?trace|трасс\w*\s+правил|\bpolicy_v\d", re.IGNORECASE)),
    ("ratios", re.compile(r"\bltv\b|\bdscr\b|\bpd\b|вероятност\w*\s+дефолт", re.IGNORECASE)),
    ("thresholds", re.compile(r"порог\w*|коэффициент\w*|надбавк\w*\s+за", re.IGNORECASE)),
    ("factors", re.compile(r"фактор\w*\s+(?:скоринг|модел|оценк)|скоркарт", re.IGNORECASE)),
    (
        "system",
        re.compile(r"системн\w+\s+(?:промпт|инструкц)|\bprompt\b|промпт|CONTEXT", re.IGNORECASE),
    ),
)

_PROMISE = re.compile(
    r"гарантир\w*|точно\s+одобр\w*|обязательно\s+одобр\w*|100\s*%|одобрим|будет\s+одобрен\w*|"
    r"одобрение\s+обеспечено",
    re.IGNORECASE,
)
_APPROVED = re.compile(r"(?<!не\s)(?<!не могу\s)(?<!не можем\s)\bодобрен[аоы]?\b", re.IGNORECASE)
_LETTERS = re.compile(r"[A-Za-zА-Яа-яЁё]")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# A number followed by one of these is a fact: money, rate, term.
_MEASURE = re.compile(
    r"^\s*(?:₽|руб|р\.|%|процент|мес|месяц|лет|год|дн|раб|млн|тыс|млрд)", re.IGNORECASE
)
_SMALL = Decimal(10)


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    violations: tuple[str, ...]


def check(answer: str, facts: Facts) -> Verdict:
    violations: list[str] = []
    text = answer.strip()
    if not MIN_ANSWER_CHARS <= len(text) <= MAX_ANSWER_CHARS:
        violations.append("length")
    if not _is_russian(text):
        violations.append("language")
    facts_text = facts.text
    for name, pattern in INTERNAL_TERMS:
        if pattern.search(text) and not pattern.search(facts_text):
            violations.append(f"internal:{name}")
    if _PROMISE.search(text):
        violations.append("promise")
    if facts.outcome not in (None, "APPROVE") and _APPROVED.search(text):
        violations.append("approval_claim")
    allowed = facts.allowed_numbers()
    for value, after in numbers_with_context(text):
        if value in allowed:
            continue
        # «2 рабочих дня», «3 шага», list numbering: small counts are fine
        # unless they read as money, a rate or a term.
        if value <= _SMALL and value == value.to_integral_value() and not _MEASURE.match(after):
            continue
        violations.append(f"number:{value:f}")
    for date in extract_dates(text) - facts.allowed_dates():
        violations.append(f"date:{date}")
    return Verdict(ok=not violations, violations=tuple(violations))


def _is_russian(text: str) -> bool:
    letters = _LETTERS.findall(text)
    if not letters:
        return False
    return len(_CYRILLIC.findall(text)) / len(letters) >= 0.8
