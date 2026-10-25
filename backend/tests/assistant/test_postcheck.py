from decimal import Decimal

import pytest

from src.modules.assistant.domain.facts import Facts, money, percent
from src.modules.assistant.domain.numbers import extract_numbers
from src.modules.assistant.domain.postcheck import check


def facts(outcome: str = "COUNTER_OFFER") -> Facts:
    f = Facts(outcome=outcome)
    f.add("Предложение банка: 1 300 000 ₽ на 60 мес., ставка 27% годовых, платёж 39 695,93 ₽.")
    f.add("Предложение действует до 29.10.2026.")
    f.add("Объяснение банка: Решение принято по результатам проверки кредитной истории.")
    return f


def test_money_and_percent_format() -> None:
    assert money(Decimal("1300000.00")) == "1 300 000 ₽"
    assert money(Decimal("39695.93")) == "39 695,93 ₽"
    assert percent(Decimal("23.50")) == "23,5%"
    assert percent(Decimal("27.00")) == "27%"


def test_the_same_number_written_differently() -> None:
    assert extract_numbers("1,3 млн ₽ и 27,00 % и 1300000") == {Decimal(1_300_000), Decimal(27)}


def test_a_faithful_answer_passes() -> None:
    answer = (
        "Банк предлагает 1,3 млн ₽ на 60 месяцев под 27% годовых, платёж 39 695,93 ₽. "
        "Предложение действует до 29.10.2026, решение можно принять в 2 шага."
    )
    assert check(answer, facts()).ok


@pytest.mark.parametrize(
    ("answer", "violation"),
    [
        ("Банк предлагает 1 500 000 ₽ на 60 мес.", "number:1500000"),
        ("Ставка будет 25% годовых.", "number:25"),
        ("Платёж около 40 000 ₽ в месяц.", "number:40000"),
        ("Предложение действует до 30.10.2026.", "date:30.10.2026"),
        ("Ваш скор 565, поэтому сумма меньше.", "internal:score"),
        ("Ваш грейд C, поэтому ставка выше.", "internal:grade"),
        ("Сработало правило LIMIT_BY_REVENUE.", "internal:reason_code"),
        ("Данные БКИ показали просрочки.", "internal:bureau"),
        ("Мы гарантируем одобрение после выписки.", "promise"),
        ("Ваша заявка одобрена на 1 300 000 ₽.", "approval_claim"),
        ("The bank offers a smaller amount.", "language"),
        ("", "length"),
        ("Да. " * 400, "length"),
    ],
)
def test_violations(answer: str, violation: str) -> None:
    verdict = check(answer, facts())
    assert not verdict.ok
    assert violation in verdict.violations


def test_terms_used_by_the_bank_itself_are_allowed() -> None:
    answer = "Банк отказал по результатам проверки кредитной истории."
    assert check(answer, facts("REJECT")).ok


def test_small_counts_are_fine_but_not_as_money() -> None:
    assert check("Осталось 3 шага.", facts()).ok
    assert not check("Платёж 3 ₽.", facts()).ok


def test_approved_is_fine_when_the_bank_approved() -> None:
    f = Facts(outcome="APPROVE")
    f.add(
        "Решение банка: заявка одобрена. Объяснение банка: Заявка одобрена на запрошенных условиях."
    )
    assert check("Ваша заявка одобрена на запрошенных условиях.", f).ok
    assert check("Нет, мы не можем одобрить её сейчас.", facts("REJECT")).ok
