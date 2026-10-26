"""Every handled event -> feed records of the right recipients."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.applications import (
    ApplicationCancelled,
    ApplicationInfoProvided,
    ApplicationSigned,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferDeclined,
)
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.clients import (
    Discrepancy,
    FinancialReportSubmitted,
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.core.messaging.contracts.decision import (
    DecisionMade,
    ManualDecisionRejected,
    PreApprovedOffersUpdated,
)
from src.core.messaging.contracts.process import (
    ProcessCompleted,
    ProcessFailed,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.modules.applications.facade import DecisionSummaryDTO, InfoRequestDTO, OfferDTO
from src.modules.decision.facade import PreApprovedOfferDTO
from src.modules.notifications.application.use_cases.project_event import ProjectEventUseCase
from src.modules.notifications.infrastructure.adapters.neighbours import FacadeNeighbours
from src.modules.notifications.infrastructure.adapters.session_facades import SessionFacades
from src.modules.notifications.infrastructure.database.models import FeedItem
from src.modules.notifications.infrastructure.repositories.feed import SqlAlchemyFeedStore
from src.modules.scoring.facade import ScoringResultDTO
from tests.fakes import builders
from tests.notifications.conftest import FeedHarness, World, decision_with_codes


def accounts(rows: list[FeedItem]) -> set[str]:
    return {r.recipient_id for r in rows if r.recipient_type == "account"}


def roles(rows: list[FeedItem]) -> set[str]:
    return {r.recipient_id for r in rows if r.recipient_type == "role"}


def members(world: World) -> set[str]:
    return {str(world.director), str(world.accountant)}


def status(
    world: World, to_status: str, from_status: str = "in_review"
) -> ApplicationStatusChanged:
    return ApplicationStatusChanged(
        application_id=world.card.id,
        organization_id=world.romashka.id,
        from_status=from_status,
        to_status=to_status,
    )


def scoring_result(application_id: UUID, *flags: str) -> ScoringResultDTO:
    return ScoringResultDTO(
        id=uuid4(),
        application_id=application_id,
        model_version="test",
        score=640,
        grade="C",
        factors=(),
        flags=flags,
        data_completeness=Decimal("0.8"),
        computed_at=builders.NOW,
    )


def decision_made(world: World, **overrides: object) -> DecisionMade:
    values: dict[str, object] = {
        "application_id": world.card.id,
        "decision_id": uuid4(),
        "outcome": "COUNTER_OFFER",
        "decided_by": "auto",
        "client_explanation": "Сумма снижена по выручке.",
    }
    values.update(overrides)
    return DecisionMade.model_validate(values)


# --- applications.events -------------------------------------------------------


async def test_submitted_goes_to_members_and_back_office(feed: FeedHarness, world: World) -> None:
    event = ApplicationSubmitted(
        application_id=world.card.id,
        organization_id=world.romashka.id,
        product_code="UNSECURED",
        amount=Decimal("3000000"),
        term_months=24,
        purpose="working_capital",
    )
    assert await feed.deliver(event) == "processed"

    rows = await feed.rows()
    client = [r for r in rows if r.audience == "client"]
    bank = [r for r in rows if r.audience == "bank"]
    assert accounts(client) == members(world)
    assert roles(bank) == {"underwriter"} and len(bank) == 1
    assert client[0].title == "Заявка № КР-2026-000001 отправлена в банк"
    assert "«Кредит без залога» на 3 000 000 ₽ на 24 мес." in client[0].body
    assert client[0].link == f"/applications/{world.card.id}"
    assert bank[0].body.startswith("ООО «Ромашка»: «Кредит без залога»")
    assert bank[0].link == f"/backoffice/applications/{world.card.id}"
    assert {r.organization_id for r in rows} == {world.romashka.id}


async def test_info_requested_carries_the_request_and_needs_action(
    feed: FeedHarness, world: World
) -> None:
    request = InfoRequestDTO(
        id=uuid4(),
        requested_fields=(),
        requested_documents=("bank_statement",),
        comment="Пришлите выписку за 12 месяцев",
        created_at=builders.NOW,
        due_at=None,
        status="open",
    )
    world.applications.add_card(replace(world.card, info_requests=(request,)))

    await feed.deliver(status(world, "info_requested"))

    rows = await feed.rows()
    assert accounts(rows) == members(world) and not roles(rows)
    row = rows[0]
    assert (row.type, row.priority, row.action_required) == ("info_requested", "high", True)
    assert row.body == "Пришлите выписку за 12 месяцев\nЗагрузите: выписка по расчётному счёту."


async def test_offer_ready_shows_the_terms(feed: FeedHarness, world: World) -> None:
    offer = OfferDTO(
        kind="counter",
        amount=Decimal("2500000"),
        term_months=24,
        rate=Decimal("24.50"),
        monthly_payment=Decimal("132178.4"),
        schedule_type="annuity",
        conditions=(),
        expires_at=builders.NOW + timedelta(days=10),
        decision_id=uuid4(),
    )
    world.applications.add_card(replace(world.card, offer=offer))

    await feed.deliver(status(world, "offer_ready"))

    row = (await feed.rows())[0]
    assert (row.type, row.action_required) == ("offer_ready", True)
    assert row.body.startswith(
        "2 500 000 ₽ на 24 мес. под 24,5 %, платёж 132 178,40 ₽ в месяц. "
        "Предложение действует до 31.10.2026."
    )


async def test_rejection_explains_with_the_client_summary(feed: FeedHarness, world: World) -> None:
    summary = DecisionSummaryDTO("REJECT", "Компания в процессе ликвидации.", ())
    world.applications.add_card(replace(world.card, decision_summary=summary))
    await feed.deliver(status(world, "rejected"))
    row = (await feed.rows())[0]
    assert row.title == "Банк не может одобрить заявку № КР-2026-000001"
    assert row.body == "Компания в процессе ликвидации."


async def test_back_to_review_after_info_has_its_own_text(feed: FeedHarness, world: World) -> None:
    await feed.deliver(status(world, "in_review", from_status="info_requested"))
    assert (await feed.rows())[0].title == "Данные по заявке № КР-2026-000001 получены"


@pytest.mark.parametrize("to_status", ["draft", "submitted"])
async def test_status_without_client_news_is_skipped(
    feed: FeedHarness, world: World, to_status: str
) -> None:
    await feed.deliver(status(world, to_status, from_status="draft"))
    assert await feed.rows() == []


@pytest.mark.parametrize(
    "event_type,title",
    [
        (OfferAccepted, "Клиент принял предложение по заявке № КР-2026-000001"),
        (OfferDeclined, "Клиент отказался от предложения по заявке № КР-2026-000001"),
        (ApplicationCancelled, "Заявка № КР-2026-000001 отменена клиентом"),
    ],
)
async def test_client_actions_are_news_for_the_back_office(
    feed: FeedHarness, world: World, event_type: type[IntegrationMessage], title: str
) -> None:
    await feed.deliver(
        event_type.model_validate(
            {"application_id": world.card.id, "organization_id": world.romashka.id}
        )
    )
    rows = await feed.rows()
    assert roles(rows) == {"underwriter"} and not accounts(rows)
    assert rows[0].title == title and rows[0].audience == "bank"


async def test_signed_and_info_provided_reach_the_back_office(
    feed: FeedHarness, world: World
) -> None:
    ids = {"application_id": world.card.id, "organization_id": world.romashka.id}
    await feed.deliver(ApplicationSigned(**ids, signed_by=world.director))
    await feed.deliver(
        ApplicationInfoProvided(**ids, info_request_id=uuid4(), document_ids=[uuid4(), uuid4()])
    )
    rows = await feed.rows()
    assert roles(rows) == {"underwriter"} and len(rows) == 2
    assert "документов: 2" in rows[1].body


# --- process.events ------------------------------------------------------------


def step(world: World, stage: str | None, node: str = "fetch") -> StepCompleted:
    return StepCompleted(
        process_id=uuid4(),
        application_id=world.card.id,
        node_id=node,
        step_code=node,
        client_stage=stage,
    )


async def test_step_completed_updates_the_stage_record(feed: FeedHarness, world: World) -> None:
    await feed.deliver(step(world, "Проверяем данные о компании"))
    first = {r.recipient_id: r for r in await feed.rows()}
    assert set(first) == members(world)
    async with feed.session_factory() as session:
        row = await session.get(FeedItem, first[str(world.director)].id)
        assert row is not None
        row.read_at = feed.clock.now()
        await session.commit()

    feed.clock.advance(timedelta(minutes=5))
    await feed.deliver(step(world, "Оцениваем финансовое положение", node="score"))

    rows = await feed.rows()
    assert len(rows) == 2, "a stage replaces the previous one instead of piling up"
    second = {r.recipient_id: r for r in rows}
    director = second[str(world.director)]
    assert director.id == first[str(world.director)].id
    assert director.title == "Оцениваем финансовое положение"
    assert director.type == "stage_changed"
    assert director.seq > max(r.seq for r in first.values()), "moved to the top of the stream"
    assert director.read_at is None, "a new stage is unread again"


async def test_internal_step_is_not_shown(feed: FeedHarness, world: World) -> None:
    await feed.deliver(step(world, None))
    assert await feed.rows() == []


async def test_task_is_created_for_the_role_and_resolved_when_done(
    feed: FeedHarness, world: World
) -> None:
    task_id = uuid4()
    await feed.deliver(
        UserTaskCreated(
            task_id=task_id,
            process_id=uuid4(),
            application_id=world.card.id,
            task_type="underwriting_review",
            candidate_role="underwriter",
            due_at=builders.NOW + timedelta(days=1),
        )
    )
    [row] = await feed.rows()
    assert (row.recipient_type, row.recipient_id) == ("role", "underwriter")
    assert (row.type, row.action_required, row.priority) == ("task_assigned", True, "high")
    assert row.title == "Новая задача: проверка заявки андеррайтером"
    assert row.body == "Заявка № КР-2026-000001, ООО «Ромашка». Срок — до 22.10.2026."
    assert row.link == f"/backoffice/tasks/{task_id}"

    await feed.deliver(
        UserTaskCompleted(task_id=task_id, application_id=world.card.id, completed_by=uuid4())
    )
    [row] = await feed.rows()
    assert row.action_required is False


async def test_process_failure_alerts_the_back_office(feed: FeedHarness, world: World) -> None:
    await feed.deliver(
        ProcessFailed(process_id=uuid4(), application_id=world.card.id, reason="timeout")
    )
    [row] = await feed.rows()
    assert row.recipient_id == "underwriter" and row.action_required
    assert row.body == "Причина: timeout. Нужна ручная проверка."


async def test_not_handled_event_is_skipped(feed: FeedHarness, world: World) -> None:
    outcome = await feed.deliver(
        ProcessCompleted(process_id=uuid4(), application_id=world.card.id, outcome="APPROVE")
    )
    assert outcome == "skipped"


# --- decision.events -----------------------------------------------------------


async def test_decision_gives_advice_from_scoring_flags(feed: FeedHarness, world: World) -> None:
    world.scoring.add_result(
        scoring_result(world.card.id, "cash_gap_forecast", "revenue_unconfirmed", "unknown")
    )
    await feed.deliver(
        decision_made(world, improvement_hints=["Добавьте поручительство владельца"])
    )

    rows = await feed.rows()
    advice = [r for r in rows if r.type == "advice"]
    titles = {r.title for r in advice}
    assert titles == {
        "Прогнозируется кассовый разрыв — посмотрите кредитную линию",
        "Подтвердите выручку выпиской — условия станут лучше",
        "Как улучшить условия",
    }
    assert accounts(advice) == members(world) and len(advice) == 6
    revenue = next(r for r in advice if r.title.startswith("Подтвердите"))
    assert revenue.link == f"/applications/{world.card.id}"
    hints = next(r for r in advice if r.title == "Как улучшить условия")
    assert hints.body == "• Добавьте поручительство владельца"
    bank = [r for r in rows if r.audience == "bank"]
    assert bank[0].title == "Автоматическое решение по заявке № КР-2026-000001: контрпредложение"


async def test_advice_uses_decision_reason_codes_too(feed: FeedHarness, world: World) -> None:
    world.decision.add_decision(decision_with_codes(world.card.id, "TAX_ARREARS"))
    await feed.deliver(decision_made(world, decided_by="underwriter"))
    rows = await feed.rows()
    assert {r.title for r in rows} == {"Есть задолженность перед бюджетом"}
    assert not roles(rows), "a manual decision is not news for the bank"


async def test_cash_gap_advice_is_skipped_for_a_credit_line(
    feed: FeedHarness, world: World
) -> None:
    world.applications.add_card(replace(world.card, product_code="CREDIT_LINE"))
    world.scoring.add_result(scoring_result(world.card.id, "cash_gap"))
    await feed.deliver(decision_made(world, decided_by="underwriter"))
    assert await feed.rows() == []


async def test_manual_decision_rejected_leads_to_the_application(
    feed: FeedHarness, world: World
) -> None:
    await feed.deliver(
        ManualDecisionRejected(
            application_id=world.card.id, task_id=uuid4(), reason="rate below the floor"
        )
    )
    [row] = await feed.rows()
    assert row.recipient_id == "underwriter" and row.action_required
    # The task of the rejected decision is closed: the link goes to the application.
    assert row.link == f"/backoffice/applications/{world.card.id}"
    assert "rate below the floor" in row.body


async def test_pre_approved_offers_replace_each_other(feed: FeedHarness, world: World) -> None:
    def offer(amount: str) -> PreApprovedOfferDTO:
        return PreApprovedOfferDTO(
            "UNSECURED", Decimal(amount), Decimal("23.5"), 36, builders.today(), "оборот"
        )

    world.decision.set_pre_approved(world.romashka.id, [offer("5000000")])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    world.decision.set_pre_approved(world.romashka.id, [offer("7000000")])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))

    rows = await feed.rows()
    assert accounts(rows) == members(world) and len(rows) == 2
    assert all(
        r.body == "• Кредит без залога: до 7 000 000 ₽, ставка от 23,5 %, срок до 36 мес."
        for r in rows
    )


async def test_no_pre_approved_offers_no_record(feed: FeedHarness, world: World) -> None:
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    assert await feed.rows() == []


def pre_approved_offer(basis: str = "оборот") -> PreApprovedOfferDTO:
    return PreApprovedOfferDTO(
        "UNSECURED", Decimal("5000000"), Decimal("23.5"), 36, builders.today(), basis
    )


def lose_verification(world: World, status: str = "mismatch") -> None:
    """The registry check of the company failed: decision withdraws the offers."""
    world.clients.add_organization(replace(world.romashka, verification_status=status))
    world.decision.set_pre_approved(world.romashka.id, [])


async def test_pre_approval_withdrawn_replaces_the_old_record(
    feed: FeedHarness, world: World
) -> None:
    world.decision.set_pre_approved(world.romashka.id, [pre_approved_offer()])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    [first, _] = await feed.rows()
    lose_verification(world)
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))

    rows = await feed.rows()
    assert accounts(rows) == members(world) and len(rows) == 2
    for row in rows:
        assert row.title == "Уточните данные компании"
        assert row.type == "advice" and row.audience == "client"
        assert row.link == f"/organizations/{world.romashka.id}"
        assert row.group_key == f"pre-approved:{world.romashka.id}"
        assert row.read_at is None
        assert "предодобрен" not in row.title.lower()
    assert min(r.seq for r in rows) > first.seq


async def test_pre_approval_withdrawn_is_said_once(feed: FeedHarness, world: World) -> None:
    world.decision.set_pre_approved(world.romashka.id, [pre_approved_offer()])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    lose_verification(world, "unverified")
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    before = {r.id: r.seq for r in await feed.rows()}
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))

    assert {r.id: r.seq for r in await feed.rows()} == before


async def test_pre_approval_withdrawn_without_a_record_stays_silent(
    feed: FeedHarness, world: World
) -> None:
    lose_verification(world)
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    assert await feed.rows() == []


async def test_no_offers_of_a_verified_company_keep_the_record(
    feed: FeedHarness, world: World
) -> None:
    world.decision.set_pre_approved(world.romashka.id, [pre_approved_offer()])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    world.decision.set_pre_approved(world.romashka.id, [])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))

    rows = await feed.rows()
    assert len(rows) == 2 and all(
        r.title == "Для вас есть предодобренные предложения" for r in rows
    )


async def test_startup_project_offer_survives_the_registry_mismatch(
    feed: FeedHarness, world: World
) -> None:
    """Estimate offers are withdrawn, the project offer of a startup stays: the
    facade returns it, so the record is the usual list of offers."""
    world.decision.set_pre_approved(world.romashka.id, [pre_approved_offer()])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))
    lose_verification(world)
    world.decision.set_pre_approved(world.romashka.id, [pre_approved_offer("project")])
    await feed.deliver(PreApprovedOffersUpdated(organization_id=world.romashka.id))

    rows = await feed.rows()
    assert accounts(rows) == members(world) and len(rows) == 2
    assert all(r.title == "Для вас есть предодобренные предложения" for r in rows)
    assert all(r.body.startswith("• Кредит без залога: до 5 000 000 ₽") for r in rows)


# --- clients.events ------------------------------------------------------------


async def test_company_events(feed: FeedHarness, world: World) -> None:
    org = world.romashka.id
    await feed.deliver(OrganizationVerified(organization_id=org))
    await feed.deliver(
        OrganizationVerificationMismatch(
            organization_id=org,
            discrepancies=[Discrepancy(field="head_name", declared="Петров", registry="Сидоров")],
        )
    )
    await feed.deliver(FinancialReportSubmitted(organization_id=org, period_year=2025))
    rows = await feed.rows()
    assert accounts(rows) == members(world) and len(rows) == 6
    titles = [r.title for r in rows if r.recipient_id == str(world.director)]
    assert titles == [
        "Данные компании подтверждены",
        "Данные компании расходятся с реестром",
        "Отчётность за 2025 год сохранена",
    ]
    mismatch = next(r for r in rows if r.type == "info_requested")
    assert mismatch.action_required
    assert "• руководитель: в кабинете «Петров», в реестре «Сидоров»" in mismatch.body


async def test_member_events_go_to_that_member_only(feed: FeedHarness, world: World) -> None:
    newcomer = uuid4()
    org = world.romashka.id
    await feed.deliver(MemberAdded(organization_id=org, account_id=newcomer, role="employee"))
    await feed.deliver(
        MemberRoleChanged(organization_id=org, account_id=newcomer, role="accountant")
    )
    await feed.deliver(MemberRemoved(organization_id=org, account_id=newcomer))
    rows = await feed.rows()
    assert accounts(rows) == {str(newcomer)}
    assert [r.title for r in rows] == [
        "Вас добавили в компанию ООО «Ромашка»",
        "Ваша роль в компании ООО «Ромашка» изменена",
        "Доступ к компании ООО «Ромашка» закрыт",
    ]
    assert rows[1].body == "Новая роль: бухгалтер."
    assert rows[1].organization_id == org and rows[1].link == f"/organizations/{org}"
    # the former member can no longer open the company: the record is not bound to it
    assert rows[2].organization_id is None and rows[2].link is None


# --- idempotency, escaping, degradation ----------------------------------------


async def test_redelivered_event_adds_nothing(feed: FeedHarness, world: World) -> None:
    event_id = uuid4()
    event = status(world, "in_review")
    assert await feed.deliver(event, event_id) == "processed"
    assert await feed.deliver(event, event_id) == "duplicate"
    assert len(await feed.rows()) == 2


async def test_projector_replay_without_inbox_adds_nothing(
    session_factory: async_sessionmaker[AsyncSession], registry: FacadeRegistry, world: World
) -> None:
    """The UNIQUE (source_event_id, recipient) key, not only the inbox, keeps it single."""
    event_id = uuid4()
    world.scoring.add_result(scoring_result(world.card.id, "cash_gap"))
    event = decision_made(world)
    written = []
    for _ in range(2):
        async with session_factory() as session:
            projector = ProjectEventUseCase(
                SqlAlchemyFeedStore(session), FacadeNeighbours(SessionFacades(registry, session))
            )
            written.append(await projector.execute(event, event_id, builders.NOW))
            await session.commit()
    assert written == [3, 0]


async def test_substituted_values_are_escaped(feed: FeedHarness, world: World) -> None:
    hostile = replace(world.romashka, name='<img src=x onerror="alert(1)">')
    world.clients.add_organization(hostile)
    world.applications.add_card(replace(world.card, org_snapshot=hostile))
    await feed.deliver(
        ProcessFailed(process_id=uuid4(), application_id=world.card.id, reason="<script>x</script>")
    )
    await feed.deliver(OrganizationVerified(organization_id=world.romashka.id))
    rows = await feed.rows()
    assert rows[0].body == "Причина: &lt;script&gt;x&lt;/script&gt;. Нужна ручная проверка."
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in rows[1].body
    assert all("<" not in r.title + r.body for r in rows)


async def test_missing_neighbours_degrade_the_text(
    session_factory: async_sessionmaker[AsyncSession], world: World
) -> None:
    """No facade registered at all: bank news still go out, without the number;
    without clients the company members are unknown — no client records."""
    harness = FeedHarness(session_factory, FacadeRegistry(), FrozenClock(builders.NOW))
    await harness.deliver(
        ApplicationSubmitted(
            application_id=world.card.id,
            organization_id=world.romashka.id,
            product_code="UNSECURED",
            amount=Decimal("1500000"),
            term_months=12,
            purpose="working_capital",
        )
    )
    await harness.deliver(step(world, "Проверяем данные о компании"))
    [row] = await harness.rows()
    assert row.recipient_id == "underwriter"
    assert row.title == "Новая заявка"
    assert row.body == "Клиент: «UNSECURED», 1 500 000 ₽ на 12 мес."


async def test_unknown_application_degrades_too(feed: FeedHarness) -> None:
    await feed.deliver(ProcessFailed(process_id=uuid4(), application_id=uuid4(), reason="timeout"))
    [row] = await feed.rows()
    assert row.title == "Процесс по заявке остановлен" and row.organization_id is None
