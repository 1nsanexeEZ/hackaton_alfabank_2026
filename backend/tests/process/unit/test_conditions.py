from decimal import Decimal

import pytest

from src.process.domain.conditions import Condition, ConditionError
from src.process.domain.context import CONDITION_FIELDS

FIELDS = {"outcome", "risk_grade", "cash_gap_flag", "info_requests_count", "complete", "stage"}


def check(source: str, **context: object) -> bool:
    return Condition(source, FIELDS)(context)


@pytest.mark.parametrize(
    "source,context,expected",
    [
        ('outcome == "APPROVE"', {"outcome": "APPROVE"}, True),
        ('outcome != "APPROVE"', {"outcome": "REJECT"}, True),
        ('outcome in ["APPROVE", "COUNTER_OFFER"]', {"outcome": "COUNTER_OFFER"}, True),
        ('outcome not in ["APPROVE"]', {"outcome": "REJECT"}, True),
        ("info_requests_count < 2", {"info_requests_count": 1}, True),
        ("info_requests_count >= 2", {"info_requests_count": 2}, True),
        ("info_requests_count > 2.5", {"info_requests_count": Decimal("3")}, True),
        ("complete == false", {"complete": False}, True),
        ("complete == false", {"complete": None}, False),
        ("complete == null", {}, True),
        ("cash_gap_flag", {"cash_gap_flag": True}, True),
        ("not cash_gap_flag", {"cash_gap_flag": None}, True),
        (
            'risk_grade in ["D", "E"] or cash_gap_flag == true and outcome == "APPROVE"',
            {"risk_grade": "A", "cash_gap_flag": True, "outcome": "APPROVE"},
            True,
        ),
        (
            '(risk_grade in ["D", "E"] or cash_gap_flag == true) and outcome == "APPROVE"',
            {"risk_grade": "A", "cash_gap_flag": True, "outcome": "REJECT"},
            False,
        ),
        ('stage == "Проверяем \\"данные\\""', {"stage": 'Проверяем "данные"'}, True),
        # ordering with a missing value is never true
        ("info_requests_count < 2", {"info_requests_count": None}, False),
        ("info_requests_count == 1", {"info_requests_count": 1}, True),
    ],
)
def test_evaluation(source: str, context: dict, expected: bool) -> None:
    assert check(source, **context) is expected


@pytest.mark.parametrize(
    "source",
    [
        "",
        "outcome ==",
        'outcome == "APPROVE" and',
        "outcome in APPROVE",
        "(outcome == 1",
        "unknown_field == 1",
        "__import__('os').system('id')",
        "outcome.__class__",
        "outcome == 'APPROVE'",
        "1 + 1",
    ],
)
def test_rejected_sources(source: str) -> None:
    with pytest.raises(ConditionError):
        Condition(source, FIELDS)


def test_fields_are_reported() -> None:
    condition = Condition('outcome == "X" or risk_grade == "A"', FIELDS)
    assert condition.fields == {"outcome", "risk_grade"}


def test_context_fields_are_allowed() -> None:
    assert {"outcome", "complete", "info_requests_count", "risk_grade"} <= CONDITION_FIELDS
    assert "decision" not in CONDITION_FIELDS  # nested payloads are not for routing
