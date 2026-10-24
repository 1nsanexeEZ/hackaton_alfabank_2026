from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain import Money
from src.modules.applications.domain.value_objects import DecisionSummary, Offer
from src.modules.applications.infrastructure.database.models import SignatureRecord
from tests.applications.api.conftest import PASSWORD, World
from tests.applications.unit.factories import offer as make_offer


def offer_for(world: World) -> Offer:
    return replace(make_offer(), expires_at=world.clock.now() + timedelta(days=7))


def offer_hash(world: World, application_id: str, account_id: UUID | None = None) -> str:
    """What the client saw in the contract before signing."""
    contract = world.client.get(
        f"/applications/{application_id}/contract",
        headers=world.headers(account_id or world.director),
    )
    assert contract.status_code == 200, contract.text
    return contract.json()["offer_hash"]


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
        f"/applications/{application['id']}/sign",
        json={"password": PASSWORD, "offer_hash": offer_hash(world, application["id"])},
        headers=accountant,
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

    seen = offer_hash(world, application["id"])
    wrong = world.client.post(
        f"/applications/{application['id']}/sign",
        json={"password": "nope", "offer_hash": seen},
        headers=headers,
    )
    assert wrong.status_code == 422
    assert wrong.json()["details"] == {"code": "invalid_password"}

    signed = world.client.post(
        f"/applications/{application['id']}/sign",
        json={"password": PASSWORD, "offer_hash": seen},
        headers={**headers, "User-Agent": "pytest", "X-Real-IP": "203.0.113.7"},
    )
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["application"]["status"] == "signed"
    signature = body["signature"]
    assert signature["simulated"] is True
    assert signature["edo_document_id"] == f"SIM-{signature['offer_hash'][:16]}"
    assert signature["offer_hash"] == seen
    assert world.outbox_types()[-1] == "ApplicationSigned"

    async def stored_signature() -> SignatureRecord | None:
        async with world.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
            return await session.get(SignatureRecord, UUID(application["id"]))

    record = world.run(stored_signature)
    assert (record.ip, record.user_agent) == ("203.0.113.7", "pytest")
    assert record.signed_by == world.director
    assert record.offer_hash == signature["offer_hash"]

    again = world.client.post(
        f"/applications/{application['id']}/sign",
        json={"password": PASSWORD, "offer_hash": seen},
        headers=headers,
    )
    assert again.status_code == 409


def accepted(world: World) -> str:
    application = world.submit(world.ready())
    to_offer(world, application["id"])
    world.client.post(
        f"/applications/{application['id']}/offer/accept", headers=world.headers(world.director)
    )
    return application["id"]


def test_contract_is_shown_from_signing_on(world: World) -> None:
    application = world.submit(world.ready())
    to_offer(world, application["id"])
    headers = world.headers(world.director)
    url = f"/applications/{application['id']}/contract"

    not_yet = world.client.get(url, headers=headers)
    assert not_yet.status_code == 409
    assert not_yet.json()["details"]["code"] == "contract_not_ready"

    world.client.post(f"/applications/{application['id']}/offer/accept", headers=headers)
    contract = world.client.get(url, headers=headers)
    assert contract.status_code == 200, contract.text
    body = contract.json()
    assert body["number"] == application["number"]
    assert body["status"] == "unsigned" and body["signature"] is None
    assert body["borrower"]["inn"] == "7701158817"
    assert body["terms"]["kind"] == "as_requested"
    schedule = body["schedule"]
    assert (schedule["term_months"], schedule["repayment"]) == (24, "annuity")
    assert Decimal(schedule["amount"]) == Decimal(body["terms"]["amount"])
    assert len(schedule["payments"]) == 24
    # only the director holds the right to sign; the accountant has no power of attorney
    assert [s["account_id"] for s in body["signers"]] == [str(world.director)]

    # another company's member does not see the contract
    stranger = world.client.get(url, headers=world.headers(world.petrov))
    assert stranger.status_code == 404


def test_signers_say_why_they_may_sign(world: World) -> None:
    """The head by the registry signs by law; anyone else holding the right
    has a power of attorney."""
    head_name = world.clients.organizations[world.romashka].head_name
    assert head_name is not None
    last, first, *middle = head_name.split()
    director = world.identity.accounts[world.director]
    world.identity.accounts[world.director] = replace(
        director, last_name=last, first_name=first, middle_name=middle[0] if middle else None
    )
    world.clients.add_member(
        world.accountant,
        world.romashka,
        "accountant",
        permissions=frozenset({"view", "submit_application", "sign"}),
    )
    application_id = accepted(world)

    body = world.client.get(
        f"/applications/{application_id}/contract", headers=world.headers(world.director)
    ).json()
    signers = {s["account_id"]: (s["name"], s["authority"]) for s in body["signers"]}
    assert signers[str(world.director)] == (head_name, "registry")
    assert signers[str(world.accountant)][1] == "power_of_attorney"


def test_signed_contract_shows_the_signature(world: World) -> None:
    application_id = accepted(world)
    headers = world.headers(world.director)
    seen = offer_hash(world, application_id)
    signed = world.client.post(
        f"/applications/{application_id}/sign",
        json={"password": PASSWORD, "offer_hash": seen},
        headers=headers,
    )
    assert signed.status_code == 200, signed.text

    body = world.client.get(f"/applications/{application_id}/contract", headers=headers).json()
    assert body["status"] == "signed"
    assert body["offer_hash"] == seen
    signature = body["signature"]
    assert signature["signed_by"] == str(world.director)
    assert signature["edo_document_id"] == f"SIM-{seen[:16]}"
    assert signature["simulated"] is True


def test_signing_a_changed_offer_is_refused(world: World) -> None:
    application_id = accepted(world)
    headers = world.headers(world.director)
    seen = offer_hash(world, application_id)

    def change_offer(app) -> None:  # type: ignore[no-untyped-def]
        app.offer = replace(app.offer, rate=Decimal("30"))

    world.process(application_id, change_offer)

    response = world.client.post(
        f"/applications/{application_id}/sign",
        json={"password": PASSWORD, "offer_hash": seen},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["details"] == {"code": "offer_changed"}
    card = world.client.get(f"/applications/{application_id}", headers=headers).json()
    assert card["status"] == "signing"


def test_sign_requires_the_offer_hash(world: World) -> None:
    application_id = accepted(world)
    response = world.client.post(
        f"/applications/{application_id}/sign",
        json={"password": PASSWORD},
        headers=world.headers(world.director),
    )
    assert response.status_code == 422


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


def test_info_request_on_the_beneficiary_needs_the_contract(world: World) -> None:
    """Банк просит уточнить выгодоприобретателя: новый ответ «за третье лицо» требует договор."""
    application = world.submit(world.ready())
    info_request_id = uuid4()

    def ask(app) -> None:  # type: ignore[no-untyped-def]
        now = world.clock.now()
        app.start_review(now)
        app.request_info(
            info_request_id=info_request_id,
            fields=("beneficiary",),
            documents=(),
            comment="Уточните, действуете ли вы в интересах третьего лица",
            due_at=None,
            now=now,
        )

    world.process(application["id"], ask)
    headers = world.headers(world.director)
    url = f"/applications/{application['id']}"
    card = world.client.get(url, headers=headers).json()
    answered = world.client.patch(
        url,
        json={
            "version": card["version"],
            "beneficiary": {
                "acts_for_third_party": True,
                "beneficiary": {"kind": "person", "name": "Посредников Павел Павлович"},
                "basis": "mandate",
            },
        },
        headers=headers,
    )
    assert answered.status_code == 200, answered.text

    answer_url = f"{url}/info-requests/{info_request_id}/answer"
    refused = world.client.post(answer_url, headers=headers)
    assert refused.status_code == 422
    assert refused.json()["details"]["violations"] == [
        {
            "code": "missing",
            "field": "documents.beneficiary_contract",
            "type": "beneficiary_contract",
            "basis": "mandate",
        }
    ]

    world.upload(card, "beneficiary_contract", content=b"%PDF-1.7", content_type="application/pdf")
    assert world.client.post(answer_url, headers=headers).status_code == 200


def test_amount_stays_decimal(world: World) -> None:
    application = world.create()
    body = world.client.patch(
        f"/applications/{application['id']}",
        json={"version": 1, "request": {"amount": "1234567.89"}},
        headers=world.headers(world.director),
    ).json()
    assert body["request"]["amount"] == "1234567.89"
    assert Money.of(body["request"]["amount"]) == Money.of("1234567.89")
