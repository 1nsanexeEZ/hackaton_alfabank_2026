from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from src.modules.applications.domain.contract_documents import (
    SigningEvent,
    SigningEventKind,
    chain_is_intact,
    deal_uid,
)
from src.modules.applications.infrastructure.contract_pdf.money import money, rubles_in_words

NOW = datetime(2026, 10, 24, 9, 35, tzinfo=UTC)


def test_deal_uid_is_the_uuid_and_its_check_symbol() -> None:
    # One 1 at the 32nd digit, weight 2 → 2.
    assert deal_uid(UUID(int=1)) == "00000000-0000-0000-0000-000000000001-2"
    # 15 × (3 × 55 + 1 + 2) = 2520, 2520 mod 16 = 8.
    assert deal_uid(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")).endswith("-8")
    uid = deal_uid(uuid4())
    assert len(uid) == 38 and uid[36] == "-" and uid[37] in "0123456789abcdef"


def _chain() -> list[SigningEvent]:
    application_id = uuid4()
    events: list[SigningEvent] = []
    for minute, kind in enumerate(SigningEventKind):
        events.append(
            SigningEvent.after(
                events[-1] if events else None,
                application_id,
                NOW + timedelta(minutes=minute),
                kind,
                "Банк, автоматически",
                {"step": minute},
            )
        )
    return events


def test_signing_log_holds_together() -> None:
    events = _chain()

    assert chain_is_intact(events)
    assert [e.seq for e in events] == [1, 2, 3]
    assert events[1].prev_hash == events[0].hash


def test_a_changed_or_dropped_entry_breaks_the_log() -> None:
    events = _chain()

    changed = [events[0], replace(events[1], details={"step": 99}), events[2]]
    assert not chain_is_intact(changed)
    assert not chain_is_intact([events[0], events[2]])


def test_the_log_survives_a_database_without_time_zones() -> None:
    """SQLite gives the time back without the zone: the hash must not change."""
    events = _chain()
    naive = [replace(e, at=e.at.replace(tzinfo=None)) for e in events]

    assert chain_is_intact(naive)


def test_amounts_are_written_as_a_contract_writes_them() -> None:
    assert money(Decimal("3000000")) == "3 000 000,00"
    assert rubles_in_words(Decimal("3000000")) == "три миллиона рублей 00 копеек"
    assert (
        rubles_in_words(Decimal("1521.05")) == "одна тысяча пятьсот двадцать один рубль 05 копеек"
    )
    assert rubles_in_words(Decimal("2002000.5")) == "два миллиона две тысячи рублей 50 копеек"
    assert rubles_in_words(Decimal("12")) == "двенадцать рублей 00 копеек"
