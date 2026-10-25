"""Intent router on rules: keywords and regular expressions, no model.

A small model on a CPU is bad at choosing tools, so the code decides what the
question is about and which data to collect; the model only words the answer.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class Intent(StrEnum):
    INJECTION = "injection"
    INTERNAL_DATA = "internal_data"
    PAYMENT = "payment"
    DECISION = "decision"
    STATUS = "status"
    PRODUCTS = "products"
    GREETING = "greeting"
    OFF_TOPIC = "off_topic"


# Attempts to change the assistant's rules or pull its instructions out.
_INJECTION = re.compile(
    r"игнорир\w*|забудь\w*\s+(?:все|всё|предыдущ|инструкц|правил)|"
    r"(?:предыдущ|прошл)\w*\s+инструкц|системн\w*\s+(?:промпт|подсказк|инструкц|сообщени)|"
    r"(?:твои|свои|ваши)\s+инструкц|промпт|prompt|"
    r"ignore\s+(?:all|previous|the)|disregard|jailbreak|"
    r"ты\s+теперь|представь,?\s+что\s+ты|веди\s+себя\s+как|режим\s+разработчика|developer\s+mode|"
    r"\bdan\b|<\s*/?\s*(?:system|context|instructions?)\s*>|"
    r"измени\w*\s+(?:статус|решени|ставк|лимит|сумм)|"
    r"\bодобри\s+(?:мне|мою|нашу|заявк|кредит|сумм)|(?:поставь|сделай)\s+одобрени",
    re.IGNORECASE,
)

# The client may not see how the risk was measured.
_INTERNAL = re.compile(
    r"\bскор(?:инг\w*)?\b|\bscor\w*|\bбалл\w*|грейд|рейтинг|"
    r"бки|бюро\s+кредитн|кредитн\w+\s+истори|"
    r"reason[_\s]?code|rule[_\s]?trace|факторы?\s+(?:скоринг|модел|оценк)|"
    r"вероятност\w*\s+дефолт|\bpd\b|\bltv\b|\bdscr\b|порог\w*|внутренн\w+\s+(?:правил|данн|оценк)|"
    r"кредитн\w+\s+политик",
    re.IGNORECASE,
)

_PAYMENT = re.compile(
    r"сколько\s+(?:я\s+)?(?:буду\s+)?(?:плати|заплач|отдава|переплач)|"
    r"(?:ежемесячн|месячн)\w*\s+платеж|платеж\w*\s+(?:в|за)\s+месяц|"
    r"посчита|рассчита|расчет|калькулятор|переплат|график\s+платеж",
    re.IGNORECASE,
)

_DECISION = re.compile(
    r"почему|причин|решени|решил|отказ|одобр|встречн|предложени|"
    r"что\s+(?:я\s+могу\s+|мне\s+|нам\s+|можно\s+)?(?:сделать|улучшить|изменить)|как\s+(?:улучшить|увеличить|получить\s+больше)|"
    r"меньше\s+(?:чем|суммы)|не\s+(?:дали|одобрили)|альтернатив|кассов\w*\s+разрыв",
    re.IGNORECASE,
)

# Process words: they beat «почему» — «почему я не могу подписать» is about signing.
_PROCESS = re.compile(
    r"статус|где\s+(?:моя\s+|наша\s+)?заявк|что\s+с\s+(?:моей\s+|нашей\s+)?заявк|этап|"
    r"дозапрос|загруз\w*|выписк|подпис\w*|доверенност|сколько\s+ждать|\bскоро\b|"
    r"когда\s+(?:будет|ждать|придет|решат|ответ)",
    re.IGNORECASE,
)

_STATUS = re.compile(
    r"что\s+(?:мне\s+|нам\s+)?(?:сейчас\s+|теперь\s+)?(?:дальше|делать|нужно|надо|сделать)|"
    r"документ\w*\s+(?:нужн|проси|прося|запросил)|заявк",
    re.IGNORECASE,
)

_PRODUCTS = re.compile(
    r"кредит|займ|овердрафт|лини[яиюей]|залог|ипотек|автокредит|лизинг|рефинанс|господдерж|льготн|"
    r"продукт|ставк|процент|срок|сумм\w*|лимит|документ|оборотн|оборудован|недвижим|транспорт|"
    r"мсп|ип\b|ооо\b|выручк|поручител|аннуитет|дифференцир|досрочн",
    re.IGNORECASE,
)

_GREETING = re.compile(
    r"^\s*(?:привет\w*|здравствуй\w*|добр\w+\s+(?:день|утро|вечер)|hi|hello|"
    r"что\s+ты\s+умеешь|кто\s+ты|помоги\w*|помощь|спасибо\w*)[\s!.?,]*$",
    re.IGNORECASE,
)


def route(text: str, *, has_application: bool) -> Intent:
    """First match wins; the order puts the guards before the scenarios."""
    normalized = normalize(text)
    if _INJECTION.search(normalized):
        return Intent.INJECTION
    if _INTERNAL.search(normalized):
        return Intent.INTERNAL_DATA
    if _PAYMENT.search(normalized):
        return Intent.PAYMENT
    if _GREETING.match(normalized):
        return Intent.GREETING
    if _PROCESS.search(normalized):
        return Intent.STATUS
    if _DECISION.search(normalized) and (has_application or "заявк" in normalized):
        return Intent.DECISION
    if _STATUS.search(normalized):
        # «Какие документы нужны для кредита под залог?» without an application
        # is about the catalog, not about a case.
        if not has_application and "заявк" not in normalized and _PRODUCTS.search(normalized):
            return Intent.PRODUCTS
        return Intent.STATUS
    if _PRODUCTS.search(normalized) or _DECISION.search(normalized):
        return Intent.PRODUCTS
    return Intent.OFF_TOPIC


def normalize(text: str) -> str:
    return text.replace("ё", "е").replace("Ё", "Е").strip()


@dataclass(frozen=True, slots=True)
class PaymentQuery:
    amount: Decimal | None
    term_months: int | None


_MULTIPLIERS = {
    "млрд": Decimal(1_000_000_000),
    "млн": Decimal(1_000_000),
    "миллион": Decimal(1_000_000),
    "тыс": Decimal(1_000),
    "тысяч": Decimal(1_000),
    "к": Decimal(1_000),
}
_AMOUNT = re.compile(
    r"(\d{1,3}(?:[   ]\d{3})+|\d+(?:[.,]\d+)?)\s*"
    r"(млрд|млн|миллион\w*|тыс\w*|к\b)?\s*(?:₽|руб\w*|р\.)?",
    re.IGNORECASE,
)
_TERM = re.compile(
    r"(\d+(?:[.,]5)?|полгода|год|полтора\s+года)\s*(мес\w*|лет|год\w*)?", re.IGNORECASE
)


def parse_payment_query(text: str) -> PaymentQuery:
    """Amount and term from free text: «3 млн на 2 года», «500 тыс. на 12 месяцев»."""
    normalized = normalize(text).lower()
    term = _parse_term(normalized)
    amount: Decimal | None = None
    for match in _AMOUNT.finditer(normalized):
        digits, unit = match.group(1), match.group(2)
        after = normalized[match.end(1) : match.end(1) + 8]
        if re.match(r"\s*(?:мес|лет|год)", after):
            continue
        value = _to_decimal(digits)
        if value is None:
            continue
        if unit:
            key = next((k for k in _MULTIPLIERS if unit.lower().startswith(k)), None)
            value *= _MULTIPLIERS[key] if key else 1
        if value >= 10_000:
            amount = value
            break
    return PaymentQuery(amount=amount, term_months=term)


def _parse_term(text: str) -> int | None:
    if re.search(r"полтора\s+года", text):
        return 18
    if re.search(r"\bполгода\b", text):
        return 6
    match = re.search(r"(\d+(?:[.,]5)?)\s*(мес\w*|лет|год\w*)", text)
    if match:
        value = _to_decimal(match.group(1))
        if value is None:
            return None
        months = value if match.group(2).startswith("мес") else value * 12
        return int(months)
    if re.search(r"\bна\s+год\b", text):
        return 12
    return None


def _to_decimal(raw: str) -> Decimal | None:
    cleaned = re.sub(r"[   ]", "", raw).replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
