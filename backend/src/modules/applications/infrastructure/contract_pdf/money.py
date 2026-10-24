"""Amounts as a contract writes them: «3 000 000,00 ₽ (три миллиона рублей 00 копеек)»."""

from decimal import ROUND_HALF_UP, Decimal

_ONES_MALE = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_ONES_FEMALE = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_TEENS = [
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
]
_TENS = [
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
]
_HUNDREDS = [
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
]
# (one, few, many), feminine
_SCALES = [
    (("", "", ""), False),
    (("тысяча", "тысячи", "тысяч"), True),
    (("миллион", "миллиона", "миллионов"), False),
    (("миллиард", "миллиарда", "миллиардов"), False),
]


def plural(number: int, forms: tuple[str, str, str]) -> str:
    if number % 100 in range(11, 15):
        return forms[2]
    return {1: forms[0], 2: forms[1], 3: forms[1], 4: forms[1]}.get(number % 10, forms[2])


def _triple(number: int, female: bool) -> list[str]:
    words = [_HUNDREDS[number // 100]]
    rest = number % 100
    if 10 <= rest < 20:
        words.append(_TEENS[rest - 10])
    else:
        words.append(_TENS[rest // 10])
        words.append((_ONES_FEMALE if female else _ONES_MALE)[rest % 10])
    return [w for w in words if w]


def rubles_in_words(amount: Decimal) -> str:
    value = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rubles, kopecks = int(value), int((value - int(value)) * 100)
    if rubles == 0:
        words = ["ноль"]
    else:
        words = []
        for scale, ((one, few, many), female) in reversed(list(enumerate(_SCALES))):
            part = rubles // 1000**scale % 1000
            if part == 0:
                continue
            words += _triple(part, female)
            if scale:
                words.append(plural(part, (one, few, many)))
    words.append(plural(rubles, ("рубль", "рубля", "рублей")))
    return f"{' '.join(words)} {kopecks:02d} {plural(kopecks, ('копейка', 'копейки', 'копеек'))}"


def money(amount: Decimal) -> str:
    """3000000 → «3 000 000,00» with non-breaking spaces between thousands."""
    value = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, fraction = f"{value:.2f}".split(".")
    return f"{int(whole):,}".replace(",", " ") + "," + fraction
