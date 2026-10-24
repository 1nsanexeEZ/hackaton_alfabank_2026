"""RecordManualDecision: проверки андеррайтера, новое решение поверх авторешения, отказы."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.messaging.contracts.decision import DecisionMade, ManualDecisionRejected
from tests.decision.runtime.decision_runtime_world import (
    TASK,
    UNDERWRITER,
    Sessions,
    by_command,
    client_view,
    decision,
    make_decision,
    manual_command,
    record_manual,
    stored_count,
)
from tests.decision.unit.decision_world import NOW, DecisionWorld, build_world


async def _reviewed(sessions: Sessions, name: str = "s3_vector") -> tuple[DecisionWorld, str]:
    """Заявка, которую автоматика отдала андеррайтеру; возвращает мир и id авторешения."""
    world = await build_world(name, acts_for_itself=True)
    [auto] = (await make_decision(sessions, world)).of_type(DecisionMade)
    assert auto.outcome == "MANUAL_REVIEW"
    return world, str(auto.decision_id)


async def test_counter_offer_overrides_the_automatic_decision(session_factory: Sessions) -> None:
    world, auto_id = await _reviewed(session_factory)
    event_id = uuid4()
    command = manual_command(
        world,
        "COUNTER_OFFER",
        amount="8000000",
        term=24,
        rate="25.5",
        conditions=("Поручительство собственника",),
    )

    outbox = await record_manual(session_factory, world, command, event_id)

    [staged] = outbox.messages
    assert staged.causation_id == event_id
    made = staged.message
    assert isinstance(made, DecisionMade)
    assert made.outcome == "COUNTER_OFFER" and made.decided_by == "underwriter"
    assert made.offer is not None and made.offer.kind == "counter"
    assert (made.offer.amount, made.offer.term_months, made.offer.rate) == (
        Decimal(8_000_000),
        24,
        Decimal("25.5"),
    )
    # CREDIT_LINE гасится процентами: первый платёж — проценты за месяц.
    assert made.offer.schedule_type == "interest_only"
    expected = world.products.calculate_payment(
        Decimal(8_000_000), 24, Decimal("25.5"), "interest_only"
    )
    assert made.offer.monthly_payment == expected.monthly_payment
    assert made.offer.conditions == ["Поручительство собственника"]
    assert made.offer.expires_at == NOW + timedelta(days=7)

    manual = await decision(session_factory, world.application_id)
    assert manual is not None and manual.id == made.decision_id
    assert str(manual.override_of) == auto_id
    assert manual.decided_by_type == "underwriter" and manual.decided_by_id == UNDERWRITER
    assert manual.comment == "Проверил выписку и договоры, риск приемлемый"
    assert {hit.rule for hit in manual.rule_trace} >= {"manual.product_bounds", "manual.authority"}
    # Авторешение не удаляется — это аудит.
    assert await stored_count(session_factory, world.application_id) == 2
    view = await client_view(session_factory, world.application_id)
    assert view is not None and view.outcome == "COUNTER_OFFER"
    assert "Проверил" not in view.client_explanation


async def test_manual_override_points_at_the_latest_automatic_decision(
    session_factory: Sessions,
) -> None:
    world, first_auto = await _reviewed(session_factory)
    await record_manual(
        session_factory, world, manual_command(world, "REQUEST_INFO", documents=("lease",))
    )
    # Клиент ответил, процесс снова просит решение, автоматика снова отдаёт андеррайтеру.
    [second_auto] = (await make_decision(session_factory, world)).of_type(DecisionMade)

    [final] = (
        await record_manual(
            session_factory,
            world,
            manual_command(world, "APPROVE", amount="10000000", term=24, rate="24"),
        )
    ).of_type(DecisionMade)

    latest = await decision(session_factory, world.application_id)
    assert latest is not None and latest.id == final.decision_id
    assert latest.override_of == second_auto.decision_id
    assert str(latest.override_of) != first_auto
    assert final.offer is not None and final.offer.kind == "as_requested"
    assert await stored_count(session_factory, world.application_id) == 4


async def test_manual_request_info_and_reject(session_factory: Sessions) -> None:
    world, _ = await _reviewed(session_factory)

    [asked] = (
        await record_manual(
            session_factory, world, manual_command(world, "REQUEST_INFO", documents=("lease",))
        )
    ).of_type(DecisionMade)
    [rejected] = (
        await record_manual(session_factory, world, manual_command(world, "REJECT"))
    ).of_type(DecisionMade)

    assert asked.requested_info is not None and asked.requested_info.documents == ["lease"]
    assert "договор аренды" in asked.client_explanation
    assert asked.offer is None
    assert rejected.offer is None and rejected.outcome == "REJECT"
    assert rejected.client_explanation.startswith("Специалист банка рассмотрел заявку")
    # Подсказки авторешения остаются клиенту при отказе.
    assert rejected.improvement_hints


@pytest.mark.parametrize(
    ("name", "kwargs", "reason"),
    [
        ("s3_vector", {"outcome": "APPROVE", "amount": "5000000", "comment": "  "}, "Комментарий"),
        (
            "s3_vector",
            {"outcome": "COUNTER_OFFER", "amount": "60000000"},
            "Сумма 60 000 000 ₽ вне рамок продукта",
        ),
        ("s3_vector", {"outcome": "APPROVE", "amount": "5000000", "term": 48}, "Срок 48 мес."),
        ("s3_vector", {"outcome": "APPROVE", "amount": "5000000", "rate": "15"}, "Ставка 15%"),
        (
            "s7_romashka_mortgage",
            {"outcome": "APPROVE", "amount": "60000000", "term": 120, "rate": "24"},
            "полномочий андеррайтера",
        ),
        ("s3_vector", {"outcome": "APPROVE"}, "укажите сумму, срок и ставку"),
        ("s3_vector", {"outcome": "REQUEST_INFO"}, "какие документы или данные"),
        ("s3_vector", {"outcome": "MANUAL_REVIEW"}, "снова отправить"),
    ],
    ids=[
        "no comment",
        "amount beyond product",
        "term beyond product",
        "rate beyond product",
        "beyond authority",
        "approve without terms",
        "request without documents",
        "manual review again",
    ],
)
async def test_manual_decision_is_rejected(
    session_factory: Sessions, name: str, kwargs: dict[str, object], reason: str
) -> None:
    world, auto_id = await _reviewed(session_factory, name)
    outcome = str(kwargs.pop("outcome"))
    event_id = uuid4()

    outbox = await record_manual(
        session_factory,
        world,
        manual_command(world, outcome, **kwargs),
        event_id,  # type: ignore[arg-type]
    )

    [staged] = outbox.messages
    rejected = staged.message
    assert isinstance(rejected, ManualDecisionRejected)
    assert rejected.application_id == world.application_id and rejected.task_id == TASK
    assert reason in rejected.reason
    assert staged.causation_id == event_id
    latest = await decision(session_factory, world.application_id)
    assert latest is not None and str(latest.id) == auto_id
    assert await by_command(session_factory, event_id) is None


async def test_authority_limit_is_inclusive(session_factory: Sessions) -> None:
    world, _ = await _reviewed(session_factory, "s7_romashka_mortgage")

    [made] = (
        await record_manual(
            session_factory,
            world,
            manual_command(world, "APPROVE", amount="50000000", term=120, rate="24"),
        )
    ).of_type(DecisionMade)

    assert made.offer is not None and made.offer.amount == Decimal(50_000_000)


async def test_repeated_manual_command_returns_the_same_decision(
    session_factory: Sessions,
) -> None:
    world, _ = await _reviewed(session_factory)
    command = manual_command(world, "APPROVE", amount="9000000", term=24, rate="24")
    event_id = uuid4()

    [made] = (await record_manual(session_factory, world, command, event_id)).of_type(DecisionMade)
    [again] = (await record_manual(session_factory, world, command, event_id)).of_type(DecisionMade)

    assert again == made
    assert await stored_count(session_factory, world.application_id) == 2
