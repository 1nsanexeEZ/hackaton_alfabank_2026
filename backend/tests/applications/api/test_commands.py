"""Commands of the process engine, delivered the way Kafka would: the process
writes to its outbox, the bus hands the message to the applications consumer."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select

from src.core.messaging.contracts.applications import (
    MarkDisbursed,
    OfferTerms,
    PresentOffer,
    RejectApplication,
    RequestInfo,
    StartReview,
)
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.process import StepCompleted
from src.core.messaging.outbox import OutboxRecord, SqlAlchemyOutboxWriter
from src.modules.applications.application.use_cases.commands import _INFO_REQUEST_NAMESPACE
from src.modules.applications.presentation.expiry import expire_offers
from tests.applications.api.conftest import PASSWORD, World


def send(world: World, message: IntegrationMessage) -> UUID:
    """Stage a message as the process would and deliver everything."""
    application_id: UUID = message.application_id  # type: ignore[attr-defined]
    app = world.client.app

    async def stage() -> UUID:
        async with app.state.session_factory() as session:  # type: ignore[attr-defined]
            writer = SqlAlchemyOutboxWriter(session, "process", world.clock)
            event_id = await writer.add(message, key=application_id, correlation_id=application_id)
            await session.commit()
            return event_id

    event_id = world.run(stage)
    world.run(app.state.messaging.drain)  # type: ignore[attr-defined]
    return event_id


def card(world: World, application_id: str) -> dict:
    return world.client.get(
        f"/applications/{application_id}", headers=world.headers(world.director)
    ).json()


def offer_terms(world: World, kind: str = "as_requested", days: int = 7) -> OfferTerms:
    return OfferTerms(
        kind=kind,  # type: ignore[arg-type]
        amount=Decimal("2500000"),
        term_months=24,
        rate=Decimal("24.5"),
        monthly_payment=Decimal("132000.10"),
        conditions=["Без залога"],
        expires_at=world.clock.now() + timedelta(days=days),
    )


def produced_by_applications(world: World) -> list[tuple[str, str | None]]:
    async def read() -> list[tuple[str, str | None]]:
        async with world.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
            rows = await session.scalars(select(OutboxRecord).order_by(OutboxRecord.id))
            return [
                (row.message_type, row.envelope["causation_id"])
                for row in rows
                if row.envelope["producer"] == "applications"
            ]

    return world.run(read)


def dead_letters(world: World) -> list[dict]:
    return world.client.app.state.messaging.bus.dead_letters  # type: ignore[attr-defined]


def submitted(world: World) -> str:
    return world.submit(world.ready())["id"]


def test_start_review_is_idempotent(world: World) -> None:
    application_id = submitted(world)
    command_id = send(
        world, StartReview(application_id=UUID(application_id), client_stage="Заявка принята")
    )

    body = card(world, application_id)
    assert body["status"] == "in_review"
    assert body["client_stage"] == "Заявка принята"
    events = produced_by_applications(world)
    assert events[-1] == ("ApplicationStatusChanged", str(command_id))

    # the process repeats the command (a retry after its own crash)
    send(world, StartReview(application_id=UUID(application_id)))
    assert produced_by_applications(world) == events
    assert dead_letters(world) == []


def test_request_info_opens_a_request(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    command_id = send(
        world,
        RequestInfo(
            application_id=UUID(application_id),
            requested_documents=["bank_statement"],
            comment="Нужна выписка за 6 месяцев",
            due_at=world.clock.now() + timedelta(days=5),
        ),
    )
    body = card(world, application_id)
    assert body["status"] == "info_requested"
    [request] = body["info_requests"]
    assert request["id"] == str(uuid5(_INFO_REQUEST_NAMESPACE, str(command_id)))
    assert request["requested_documents"] == ["bank_statement"]
    assert request["comment"] == "Нужна выписка за 6 месяцев"


def test_offer_is_presented(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    decision_id = uuid4()
    send(
        world,
        PresentOffer(
            application_id=UUID(application_id),
            decision_id=decision_id,
            offer=offer_terms(world, kind="counter"),
            client_explanation="Одобрили меньшую сумму: выручка подтверждает 2,5 млн",
            improvement_hints=["Подтвердите выручку выпиской"],
            alternative_product_code="OVERDRAFT",
            decided_by="auto",
        ),
    )
    body = card(world, application_id)
    assert body["status"] == "offer_ready"
    assert body["offer"]["amount"] == "2500000.00"
    assert body["offer"]["kind"] == "counter"
    # who decided is for the bank's list, the client's card does not carry it
    assert body["decision_summary"] == {
        "outcome": "COUNTER_OFFER",
        "client_explanation": "Одобрили меньшую сумму: выручка подтверждает 2,5 млн",
        "improvement_hints": ["Подтвердите выручку выпиской"],
        "alternative_product_code": "OVERDRAFT",
    }
    assert body["available_actions"] == ["accept_offer", "decline_offer", "cancel"]


def test_rejection(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    send(
        world,
        RejectApplication(
            application_id=UUID(application_id),
            client_explanation="Компания в стадии ликвидации",
        ),
    )
    body = card(world, application_id)
    assert body["status"] == "rejected"
    assert body["decision_summary"]["outcome"] == "REJECT"
    assert body["closed_at"] is not None


def test_staff_list_tells_who_decided(world: World) -> None:
    def reject(decided_by: str | None) -> str:
        application_id = submitted(world)
        send(world, StartReview(application_id=UUID(application_id)))
        send(
            world,
            RejectApplication(
                application_id=UUID(application_id),
                decision_id=uuid4(),
                client_explanation="Отказ",
                decided_by=decided_by,  # type: ignore[arg-type]
            ),
        )
        return application_id

    by_policy, by_underwriter, unknown = reject("auto"), reject("underwriter"), reject(None)
    offered = submitted(world)
    send(world, StartReview(application_id=UUID(offered)))
    send(
        world,
        PresentOffer(
            application_id=UUID(offered),
            decision_id=uuid4(),
            offer=offer_terms(world),
            client_explanation="Одобрено",
            decided_by="auto",
        ),
    )
    draft = world.create(product_code="OVERDRAFT")["id"]
    # the next save of the application keeps who decided
    world.client.post(
        f"/applications/{offered}/offer/accept", headers=world.headers(world.director)
    )

    def listed(**params: str) -> dict[str, str | None]:
        response = world.client.get("/applications", params=params, headers=world.underwriter())
        assert response.status_code == 200, response.text
        return {item["id"]: item["decided_by"] for item in response.json()}

    assert listed() == {
        by_policy: "auto",
        by_underwriter: "underwriter",
        unknown: None,
        offered: "auto",
        draft: None,
    }
    assert listed(decided_by="auto") == {by_policy: "auto", offered: "auto"}
    assert listed(decided_by="auto", status="rejected") == {by_policy: "auto"}
    assert listed(decided_by="underwriter") == {by_underwriter: "underwriter"}
    response = world.client.get(
        "/applications", params={"decided_by": "robot"}, headers=world.underwriter()
    )
    assert response.status_code == 422


def test_command_after_cancel_is_acknowledged(world: World) -> None:
    """The client cancelled while scoring was running: no error, no DLQ."""
    application_id = submitted(world)
    world.client.post(
        f"/applications/{application_id}/cancel", headers=world.headers(world.director)
    )
    before = produced_by_applications(world)
    send(
        world,
        PresentOffer(
            application_id=UUID(application_id),
            decision_id=uuid4(),
            offer=offer_terms(world),
            client_explanation="Одобрено",
        ),
    )
    assert card(world, application_id)["status"] == "cancelled"
    assert produced_by_applications(world) == before
    assert dead_letters(world) == []


def test_command_for_unknown_application(world: World) -> None:
    send(world, StartReview(application_id=uuid4()))
    assert dead_letters(world) == []


def test_disbursement_after_signing(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    send(
        world,
        PresentOffer(
            application_id=UUID(application_id),
            decision_id=uuid4(),
            offer=offer_terms(world),
            client_explanation="Одобрено",
        ),
    )
    headers = world.headers(world.director)
    world.client.post(f"/applications/{application_id}/offer/accept", headers=headers)

    # too early: not signed yet — skipped, not failed
    send(world, MarkDisbursed(application_id=UUID(application_id)))
    assert card(world, application_id)["status"] == "signing"

    contract = world.client.get(f"/applications/{application_id}/contract", headers=headers)
    world.client.post(
        f"/applications/{application_id}/sign",
        json={"password": PASSWORD, "offer_hash": contract.json()["offer_hash"]},
        headers=headers,
    )
    send(world, MarkDisbursed(application_id=UUID(application_id)))
    body = card(world, application_id)
    assert body["status"] == "disbursed"
    assert body["disbursement"]["reference"] == f"SIM-{body['number']}"
    assert body["disbursement"]["simulated"] is True

    events = produced_by_applications(world)
    send(world, MarkDisbursed(application_id=UUID(application_id)))
    assert produced_by_applications(world) == events
    assert dead_letters(world) == []


def test_client_stage_follows_the_process(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    send(
        world,
        StepCompleted(
            process_id=uuid4(),
            application_id=UUID(application_id),
            node_id="score",
            step_code="calculate_score",
            client_stage="Оцениваем заявку",
        ),
    )
    assert card(world, application_id)["client_stage"] == "Оцениваем заявку"


def test_overdue_offers_expire(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    send(
        world,
        PresentOffer(
            application_id=UUID(application_id),
            decision_id=uuid4(),
            offer=offer_terms(world, days=1),
            client_explanation="Одобрено",
        ),
    )
    session_factory = world.client.app.state.session_factory  # type: ignore[attr-defined]

    assert world.run(expire_offers, session_factory, world.clock) == 0
    world.clock.advance(timedelta(days=1, seconds=1))
    assert world.run(expire_offers, session_factory, world.clock) == 1
    assert world.run(expire_offers, session_factory, world.clock) == 0

    body = card(world, application_id)
    assert body["status"] == "expired"
    assert body["history"][-1]["actor"] == "system"
    assert produced_by_applications(world)[-1] == ("OfferExpired", None)


def test_expires_at_is_kept_with_timezone(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    terms = offer_terms(world)
    send(
        world,
        PresentOffer(
            application_id=UUID(application_id),
            decision_id=uuid4(),
            offer=terms,
            client_explanation="Одобрено",
        ),
    )
    expires = datetime.fromisoformat(card(world, application_id)["offer"]["expires_at"])
    assert expires == terms.expires_at


def test_stage_label_does_not_bump_the_version_and_empty_label_is_skipped(world: World) -> None:
    application_id = submitted(world)
    send(world, StartReview(application_id=UUID(application_id)))
    before = card(world, application_id)

    def step(stage: str | None) -> None:
        send(
            world,
            StepCompleted(
                process_id=uuid4(),
                application_id=UUID(application_id),
                node_id="node",
                step_code="calculate_score",
                client_stage=stage,
            ),
        )

    step("Оцениваем заявку")
    after = card(world, application_id)
    assert after["client_stage"] == "Оцениваем заявку"
    # a display label: no fight for the version with commands and the client
    assert after["version"] == before["version"]

    step(None)  # a step the client does not see
    assert card(world, application_id)["client_stage"] == "Оцениваем заявку"
