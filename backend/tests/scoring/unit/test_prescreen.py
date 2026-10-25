"""Предскрин учредителя стартапа по личной кредитной истории: каждое правило на границе,
истории нет — пройден, пороги — из prescreen_v1.yaml."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.enrichment.facade import CreditHistoryDTO, ObligationDTO
from src.modules.scoring.application.model_versions import FixedModel
from src.modules.scoring.domain.prescreen import PersonHistoryInput
from src.modules.scoring.infrastructure.config_loader import (
    ScorecardConfigError,
    load_pd_model,
    load_prescreen,
    load_prescreen_file,
)
from src.modules.scoring.infrastructure.facade_impl import ScoringFacadeImpl

PRESCREEN = load_prescreen()
CLEAN = PersonHistoryInput(
    current_overdue_days=0,
    max_overdue_days_12m=0,
    inquiries_last_30d=1,
    monthly_payments=Decimal("5000"),
    obligations=1,
)


def codes(history: PersonHistoryInput | None) -> dict[str, bool]:
    return {r.code: r.passed for r in PRESCREEN.check(history).reasons}


def test_clean_history_passes() -> None:
    output = PRESCREEN.check(CLEAN)
    assert output.passed and output.version == "prescreen_v1"
    assert codes(CLEAN) == {
        "no_current_overdue": True,
        "no_serious_overdue": True,
        "few_inquiries": True,
        "debt_load": True,
    }


def test_no_history_passes() -> None:
    output = PRESCREEN.check(None)
    assert output.passed and [r.code for r in output.reasons] == ["no_history"]


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"current_overdue_days": 30}, "no_current_overdue"),
        ({"max_overdue_days_12m": 91}, "no_serious_overdue"),
        ({"inquiries_last_30d": 6}, "few_inquiries"),
        ({"monthly_payments": Decimal("300000.01")}, "debt_load"),
    ],
)
def test_each_rule_fails_past_its_threshold(overrides: dict[str, object], code: str) -> None:
    history = replace(CLEAN, **overrides)  # type: ignore[arg-type]
    output = PRESCREEN.check(history)
    assert not output.passed
    assert [r.code for r in output.reasons if not r.passed] == [code]


@pytest.mark.parametrize(
    "overrides",
    [
        {"current_overdue_days": 29},
        {"max_overdue_days_12m": 90},
        {"inquiries_last_30d": 5},
        {"monthly_payments": Decimal("300000")},
    ],
)
def test_thresholds_themselves_pass(overrides: dict[str, object]) -> None:
    assert PRESCREEN.check(replace(CLEAN, **overrides)).passed  # type: ignore[arg-type]


def test_client_messages_carry_no_thresholds() -> None:
    failing = PersonHistoryInput(45, 120, 9, Decimal("500000"), 2)
    for reason in PRESCREEN.check(failing).reasons:
        assert not any(ch.isdigit() for ch in reason.message), reason.message


def test_facade_reads_the_credit_history() -> None:
    history = CreditHistoryDTO(
        obligations=(
            ObligationDTO(
                creditor="ПАО «Кредит»",
                kind="consumer",
                amount=Decimal("800000"),
                balance=Decimal("650000"),
                monthly_payment=Decimal("27000"),
                opened_at=date(2024, 3, 1),
                closes_at=date(2028, 3, 1),
                overdue_days=45,
            ),
        ),
        inquiries_last_30d=4,
        has_active_overdue=True,
        max_overdue_days_12m=45,
        total_monthly_payments=Decimal("27000"),
    )
    facade = ScoringFacadeImpl(None, FixedModel(load_pd_model()))  # type: ignore[arg-type]
    result = facade.prescreen_person(history)
    assert not result.passed
    assert [r.code for r in result.reasons if not r.passed] == ["no_current_overdue"]
    assert facade.prescreen_person(None).passed


def test_broken_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "prescreen.yaml"
    path.write_text("version: x\ncurrent_overdue_days: 0\n", encoding="utf-8")
    with pytest.raises(ScorecardConfigError):
        load_prescreen_file(path)
