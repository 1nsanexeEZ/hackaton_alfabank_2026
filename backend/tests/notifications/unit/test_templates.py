from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.notifications.domain import templates as t
from src.modules.notifications.domain.feed import FeedEntry


def test_every_substitution_is_escaped() -> None:
    title, body = t.Template("Компания {name}", "Комментарий: {comment}").render(
        name="<b>ООО</b>", comment="\"x\" & 'y'"
    )
    assert title == "Компания &lt;b&gt;ООО&lt;/b&gt;"
    assert body == "Комментарий: &quot;x&quot; &amp; &#x27;y&#x27;"


def test_rendered_fragment_is_not_escaped_twice() -> None:
    fragment = t.Template("", "<{value}>").fragment(value="&")
    assert fragment == "<&amp;>"  # template text is trusted, the value is escaped
    _, body = t.Template("", "{inner}").render(inner=fragment)
    assert body == "<&amp;>"


def test_bullets_escape_each_line() -> None:
    _, body = t.Template("", "{list}").render(list=t.bullets(["a<b", "c"]))
    assert body == "• a&lt;b\n• c"


def test_missing_number_leaves_no_gaps() -> None:
    title, body = t.STAGE.render(stage="Проверяем данные", number=t.number_label(None))
    assert title == "Проверяем данные"
    assert body == "Заявка: текущий этап рассмотрения."
    title, _ = t.SUBMITTED.render(number=t.number_label("КР-1"), product="X", amount="1", term=3)
    assert title == "Заявка № КР-1 отправлена в банк"


def test_empty_lines_are_dropped() -> None:
    _, body = t.STATUS["info_requested"].render(number="", comment="Нужна выписка", documents="")
    assert body == "Нужна выписка"


@pytest.mark.parametrize(
    "amount,text",
    [
        (Decimal("3000000"), "3 000 000 ₽"),
        (Decimal("158613.29"), "158 613,29 ₽"),
        (Decimal("1500.5"), "1 500,50 ₽"),
        (Decimal("0"), "0 ₽"),
    ],
)
def test_money(amount: Decimal, text: str) -> None:
    assert t.money(amount) == text


@pytest.mark.parametrize(
    "value,text",
    [(Decimal("23.50"), "23,5 %"), (Decimal("20"), "20 %"), (Decimal("12.25"), "12,25 %")],
)
def test_rate(value: Decimal, text: str) -> None:
    assert t.rate(value) == text


def test_day() -> None:
    assert t.day(datetime(2026, 11, 3, 23, 0, tzinfo=UTC)) == "03.11.2026"


def test_every_status_template_renders() -> None:
    values = {"number": "№ 1", "comment": "c", "documents": "", "offer": "", "explanation": "e"}
    for key, template in t.STATUS.items():
        title, _ = template.render(**values)
        assert title, key


def test_source_id_is_the_event_id_or_a_stable_derivative() -> None:
    event_id = uuid4()
    plain = FeedEntry(type="advice", audience="client", title="t", body="b")
    first = FeedEntry(
        type="advice", audience="client", title="t", body="b", discriminator="advice:a"
    )
    second = FeedEntry(
        type="advice", audience="client", title="t", body="b", discriminator="advice:b"
    )
    assert plain.source_id(event_id) == event_id
    assert first.source_id(event_id) == first.source_id(event_id)
    assert (
        len({plain.source_id(event_id), first.source_id(event_id), second.source_id(event_id)}) == 3
    )
