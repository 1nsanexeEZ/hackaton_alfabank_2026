import re
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest

from src.modules.applications.facade import ApplicationStatus
from src.modules.bff.application.actions import available_actions, todo_for
from src.modules.bff.application.client_status import ClientStatus, client_status, offer_kind_of_row
from src.modules.clients.facade import OrgPermission

FRONTEND_STATUSES = Path(__file__).parents[3] / "frontend/src/entities/application/model/status.ts"


@pytest.mark.parametrize(
    "status,stage,offer_kind,expected",
    [
        ("draft", None, None, "draft"),
        ("submitted", None, None, "submitted"),
        ("in_review", None, None, "checking"),
        ("in_review", "Заявка принята", None, "checking"),
        ("in_review", "Проверяем заявку", None, "checking"),
        ("in_review", "Проверяем данные о компании", None, "checking"),
        ("in_review", "Оцениваем залог", None, "scoring"),
        ("in_review", "Оцениваем заявку", None, "scoring"),
        ("in_review", "Подбираем условия", None, "scoring"),
        ("in_review", "Заявка у специалиста", None, "scoring"),
        ("info_requested", "Нужна информация от вас", None, "info_requested"),
        ("offer_ready", "Решение готово", "as_requested", "approved"),
        ("offer_ready", "Решение готово", "counter", "counter_offer"),
        ("offer_ready", None, None, "approved"),
        ("signing", None, "as_requested", "signing"),
        ("signed", None, "as_requested", "issued"),
        ("disbursed", None, "counter", "issued"),
        ("rejected", "Решение готово", None, "rejected"),
        ("offer_declined", None, "counter", "declined"),
        ("expired", None, None, "expired"),
        ("cancelled", None, None, "cancelled"),
    ],
)
def test_client_status_table(
    status: str, stage: str | None, offer_kind: str | None, expected: str
) -> None:
    assert client_status(status, stage, offer_kind) == expected


def test_every_backend_status_is_mapped() -> None:
    known = set(get_args(ClientStatus))
    for status in get_args(ApplicationStatus):
        assert client_status(status, None, None) in known


def test_client_statuses_cover_the_frontend_set() -> None:
    if not FRONTEND_STATUSES.exists():
        pytest.skip("frontend is not checked out")
    frontend = set(re.findall(r"^\s{2}(\w+): \{ label", FRONTEND_STATUSES.read_text("utf-8"), re.M))
    assert frontend, "status list not found in status.ts"
    assert frontend <= set(get_args(ClientStatus))
    # Statuses the frontend still has to add.
    assert set(get_args(ClientStatus)) - frontend <= {"cancelled", "declined", "expired"}


@pytest.mark.parametrize(
    "amount,offer_amount,expected",
    [
        (Decimal("3000000"), None, None),
        (Decimal("3000000"), Decimal("3000000"), "as_requested"),
        (Decimal("3000000"), Decimal("2000000"), "counter"),
        (None, Decimal("2000000"), "as_requested"),
    ],
)
def test_offer_kind_of_projector_row(
    amount: Decimal | None, offer_amount: Decimal | None, expected: str | None
) -> None:
    assert offer_kind_of_row(amount, offer_amount) == expected


def test_actions_follow_status_and_rights() -> None:
    everything = frozenset(OrgPermission)
    viewer = frozenset({OrgPermission.VIEW.value})
    accountant = frozenset({OrgPermission.VIEW.value, OrgPermission.SUBMIT_APPLICATION.value})
    assert available_actions("offer_ready", everything) == [
        "accept_offer",
        "decline_offer",
        "cancel",
    ]
    assert available_actions("offer_ready", viewer) == []
    assert available_actions("signing", accountant) == []
    assert available_actions("signing", everything) == ["sign"]
    assert available_actions("in_review", everything) == []


def test_todo_kinds() -> None:
    assert todo_for("info", "КР-1") == ("info_requested", "Банку нужны данные по заявке КР-1")
    assert todo_for("offer", "КР-1") == ("offer_ready", "Готово решение по заявке КР-1")
    assert todo_for("sign", "КР-1") == ("signing", "Подпишите договор по заявке КР-1")
    assert todo_for("none", "КР-1") is None
