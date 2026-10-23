"""Обороты в банке (АБС) во входе скоринга: сколько полных месяцев клиент в банке на дату
заявки и как это сохраняется в снимке входа."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from src.modules.enrichment.facade import BankTurnoverDTO, EnrichmentSnapshotDTO
from src.modules.scoring.application.input_builder import _bank_months
from src.modules.scoring.application.serialization import dump_input, input_hash, load_input
from tests.scoring.scenarios import SCENARIOS

ROMASHKA = SCENARIOS["romashka_s1"]
AS_OF = date(2026, 10, 21)


def snapshot(turnover: BankTurnoverDTO | None) -> EnrichmentSnapshotDTO:
    return EnrichmentSnapshotDTO(
        id=uuid4(),
        application_id=uuid4(),
        organization_id=uuid4(),
        collected_at=None,  # type: ignore[arg-type]
        sources_ok=(),
        sources_failed=(),
        egrul=None,
        fns=None,
        bki=None,
        cashflow=None,
        bank_turnover=turnover,
    )


@pytest.mark.parametrize(
    ("since", "months"),
    [
        (date(2020, 10, 24), 71),
        (date(2026, 4, 21), 6),
        (date(2026, 4, 22), 5),
        (date(2026, 10, 1), 0),
        (None, 0),  # не клиент банка
    ],
)
def test_full_months_in_the_bank(since: date | None, months: int) -> None:
    assert _bank_months(snapshot(BankTurnoverDTO(client_since=since)), AS_OF) == months


def test_no_answer_from_the_core_system_means_unknown() -> None:
    assert _bank_months(snapshot(None), AS_OF) is None


def test_snapshot_keeps_bank_months() -> None:
    inp = replace(ROMASHKA, bank_months=5)
    assert load_input(dump_input(inp)) == inp


def test_snapshot_without_bank_months_hashes_as_before() -> None:
    """Входы без оборотов АБС (и старые снимки) хешируются, как до этого поля."""
    stored = dump_input(ROMASHKA)
    assert "bank_months" not in stored
    assert load_input(stored).bank_months is None
    assert input_hash(stored) == input_hash(dump_input(replace(ROMASHKA, bank_months=None)))
