from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from src.core.domain import Money
from src.modules.applications.domain.value_objects import DecisionSummary, Offer
from src.modules.applications.infrastructure.models import SignatureRecord
from tests.applications.api.conftest import PASSWORD, World
from tests.applications.unit.factories import offer as make_offer


def offer_for(world: World) -> Offer:
    return replace(make_offer(), expires_at=world.clock.now() + timedelta(days=7))


def to_offer(world: World, application_id: str) -> None:
    def step(application) -> None:  # type: ignore[no-untyped-def]
        now = world.clock.now()
        application.start_review(now)
        application.present_offer(
            offer_for(world), DecisionSummary("APPROVE", "Заявка одобрена"), now
        )

    world.process(application_id, step)


def test_submit_freezes_the_company_snapshot(world: World) -> None:
    application = world.ready()
    submitted = world.submit(application)

    assert submitted["status"] == "submitted"
    assert submitted["submitted_at"] is not None
    assert submitted["available_actions"] == ["cancel"]
    assert submitted["organization"]["inn"] == "7701158817"

    # the bank's data about the company changes later — the application keeps its copy
    company = world.clients.organizations[world.romashka]
    world.clients.organizations[world.romashka] = replace(company, name="ООО «Ромашка-2»")
    card = world.client.get(
        f"/applications/{application['id']}", headers=world.headers(world.director)
    ).json()
    assert card["organization"]["name"] == "ООО «Ромашка»"

    assert world.outbox_types()[-2:] == ["ApplicationStatusChanged", "ApplicationSubmitted"]


def test_incomplete_application_lists_every_problem(world: World) -> None:
    application = world.create()
    response = world.client.post(
        f"/applications/{application['id']}/submit", headers=world.headers(world.director)
    )
    assert response.status_code == 422
    fields = {v["field"] for v in response.json()["details"]["violations"]}
    assert "documents.bank_statement" in fields and "request.amount" in fields
    assert world.outbox_types() == []


def test_accountant_submits_but_does_not_sign(world: World) -> None:
    """S-8: an accountant without a power of attorney prepares and submits,
    accepts the offer, but signing is for the director."""
    application = world.submit(world.ready(world.accountant), world.accountant)
    to_offer(world, application["id"])

    accountant = world.headers(world.accountant)
    card = world.client.get(f"/applications/{application['id']}", headers=accountant).json()
    assert card["available_actions"] == ["accept_offer", "decline_offer", "cancel"]
    accepted = world.client.post(
        f"/applications/{application['id']}/offer/accept", headers=accountant
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "signing"
    assert accepted.json()["available_actions"] == []  # no "sign" for the accountant

    denied = world.client.post(
        f"/applications/{application['id']}/sign", json={"password": PASSWORD}, headers=accountant
    )
    assert denied.status_code == 403

    director = world.headers(world.director)
    card = world.client.get(f"/applications/{application['id']}", headers=director).json()
    assert card["available_actions"] == ["sign"]


def test_signing_needs_the_password_again(world: World) -> None:
    application = world.submit(world.ready())
    to_offer(world, application["id"])
    headers = world.headers(world.director)
    world.client.post(f"/applications/{application['id']}/offer/accept", headers=headers)

    wrong = world.client.post(
        f"/applications/{application['id']}/sign", json={"password": "nope"}, headers=headers
    )
    assert wrong.status_code == 422
    assert wrong.json()["details"] == {"code": "invalid_password"}

    signed = world.client.post(
        f"/applications/{application['id']}/sign",
        json={"password": PASSWORD},
        headers={**headers, "User-Agent": "pytest", "X-Real-IP": "203.0.113.7"},
    )
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["application"]["status"] == "signed"
    signature = body["signature"]
    assert signature["simulated"] is True
    assert signature["edo_document_id"] == f"SIM-{signature['offer_hash'][:16]}"
    assert len(signature["offer_hash"]) == 64
    assert world.outbox_types()[-1] == "ApplicationSigned"

    async def stored_signature() -> SignatureRecord | None:
        async with world.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
            return await session.get(SignatureRecord, UUID(application["id"]))

    record = world.run(stored_signature)
    assert (record.ip, record.user_agent) == ("203.0.113.7", "pytest")
    assert record.signed_by == world.director
    assert record.offer_hash == signature["offer_hash"]

    again = world.client.post(
        f"/applications/{application['id']}/sign", json={"password": PASSWORD}, headers=headers
    )
    assert again.status_code == 409


def test_expired_offer_cannot_be_accepted(world: World) -> None:
    application = world.submit(world.ready())
    to_offer(world, application["id"])
    world.clock.advance(timedelta(days=8))
    response = world.client.post(
        f"/applications/{application['id']}/offer/accept", headers=world.headers(world.director)
    )
    assert response.status_code == 409
    assert response.json()["details"]["code"] == "offer_expired"


def test_decline_offer(world: World) -> None:
    application = world.submit(world.ready())
    to_offer(world, application["id"])
    response = world.client.post(
        f"/applications/{application['id']}/offer/decline",
        json={"reason": "Ставка высокая"},
        headers=world.headers(world.director),
    )
    assert response.json()["status"] == "offer_declined"
    assert world.outbox_types()[-1] == "OfferDeclined"


def test_information_request_round_trip(world: World) -> None:
    application = world.submit(world.ready())
    info_request_id = uuid4()

    def ask(app) -> None:  # type: ignore[no-untyped-def]
        now = world.clock.now()
        app.start_review(now)
        app.request_info(
            info_request_id=info_request_id,
            fields=(),
            documents=("financial_statement",),
            comment="Пришлите отчётность за прошлый год",
            due_at=None,
            now=now,
        )

    world.process(application["id"], ask)
    headers = world.headers(world.director)
    card = world.client.get(f"/applications/{application['id']}", headers=headers).json()
    assert card["status"] == "info_requested"
    assert card["available_actions"] == ["upload_document", "answer_info_request", "cancel"]

    answer_url = f"/applications/{application['id']}/info-requests/{info_request_id}/answer"
    too_early = world.client.post(answer_url, headers=headers)
    assert too_early.status_code == 422

    world.upload(card, "financial_statement", content=b"%PDF-1.7", content_type="application/pdf")
    answered = world.client.post(answer_url, headers=headers)
    assert answered.status_code == 200
    assert answered.json()["status"] == "in_review"
    assert answered.json()["info_requests"][0]["status"] == "answered"
    assert world.outbox_types()[-1] == "ApplicationInfoProvided"


def test_amount_stays_decimal(world: World) -> None:
    application = world.create()
    body = world.client.patch(
        f"/applications/{application['id']}",
        json={"version": 1, "request": {"amount": "1234567.89"}},
        headers=world.headers(world.director),
    ).json()
    assert body["request"]["amount"] == "1234567.89"
    assert Money.of(body["request"]["amount"]) == Money.of("1234567.89")
