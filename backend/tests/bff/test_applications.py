from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from src.core.access.permissions import Permissions
from src.modules.applications.facade import DocumentDTO, InfoRequestDTO
from tests.bff import factories
from tests.bff.conftest import World
from tests.fakes.builders import NOW

# --- list ---------------------------------------------------------------------


def test_list_comes_from_the_projector(world: World) -> None:
    for minute, status in enumerate(["draft", "in_review", "offer_ready", "rejected"]):
        world.add_application(
            status=status, number=f"КР-{minute}", updated_at=NOW + timedelta(minutes=minute)
        )
    world.add_application(world.vector, status="in_review", number="КР-ВЕКТОР")

    response = world.get(
        "/bff/applications", world.as_client(world.employee), organization_id=world.romashka.id
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 4
    assert [(r["number"], r["client_status"]) for r in body["items"]] == [
        ("КР-3", "rejected"),
        ("КР-2", "approved"),
        ("КР-1", "checking"),
        ("КР-0", "draft"),
    ]
    assert body["items"][1]["action_required"] == "offer"
    assert body["items"][1]["product_name"] == "Кредит UNSECURED"


def test_list_filters_and_pages(world: World) -> None:
    for minute in range(3):
        world.add_application(
            status="in_review", number=f"КР-{minute}", updated_at=NOW + timedelta(minutes=minute)
        )
    world.add_application(status="draft", number="КР-Ч")
    headers = world.as_client(world.director)

    filtered = world.get(
        "/bff/applications", headers, organization_id=world.romashka.id, status="in_review"
    ).json()
    paged = world.get(
        "/bff/applications",
        headers,
        organization_id=world.romashka.id,
        status="in_review",
        limit=1,
        offset=1,
    ).json()

    assert filtered["total"] == 3
    assert paged["total"] == 3
    assert [r["number"] for r in paged["items"]] == ["КР-1"]


def test_list_of_a_foreign_company_is_404(world: World) -> None:
    world.add_application(world.vector, status="in_review")

    for org_id in (world.vector.id, uuid4()):
        response = world.get(
            "/bff/applications", world.as_client(world.director), organization_id=org_id
        )
        assert response.status_code == 404


def test_list_needs_requests_read(world: World) -> None:
    headers = world.token("client", world.director, without=(Permissions.REQUESTS_READ,))

    response = world.get("/bff/applications", headers, organization_id=world.romashka.id)

    assert response.status_code == 403


def test_list_validates_paging(world: World) -> None:
    headers = world.as_client(world.director)

    response = world.get("/bff/applications", headers, organization_id=world.romashka.id, limit=0)

    assert response.status_code == 422


# --- card ---------------------------------------------------------------------


def test_card_is_assembled_from_the_owner_and_the_projector(world: World) -> None:
    open_request = InfoRequestDTO(
        id=uuid4(),
        requested_fields=(),
        requested_documents=("bank_statement",),
        comment="Нужна выписка за 6 месяцев",
        created_at=NOW,
        due_at=NOW + timedelta(days=3),
        status="open",
    )
    document = DocumentDTO(
        id=uuid4(),
        type="bank_statement",
        filename="statement.csv",
        content_type="text/csv",
        size_bytes=120,
        status="uploaded",
        uploaded_by=world.director,
        uploaded_at=NOW,
    )
    card = world.add_application(
        status="info_requested",
        client_stage="Нужна информация от вас",
        info_requests=(open_request,),
        documents=(document,),
    )
    world.projector.add_timeline_entry(
        factories.timeline_entry(card.id, "Заявка принята", minutes=1)
    )
    world.projector.add_timeline_entry(
        factories.timeline_entry(card.id, "Нужна информация от вас", minutes=3)
    )
    world.projector.add_timeline_entry(
        factories.timeline_entry(card.id, factories.BANK_TIMELINE_TITLE, "bank", minutes=2)
    )
    world.decision.add_decision(
        factories.decision(
            card.id,
            "REQUEST_INFO",
            terms=None,
            client_explanation="Нужна выписка",
            requested_info=None,
        )
    )
    world.notifications.add_item(world.director, factories.feed_item(world.romashka.id, card.id))
    world.notifications.add_item(world.director, factories.feed_item(world.romashka.id))

    response = world.get(f"/bff/applications/{card.id}", world.as_client(world.director))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] == []
    assert body["status"] == "info_requested"
    assert body["client_status"] == "info_requested"
    assert body["organization"] == {
        "id": str(world.romashka.id),
        "name": world.romashka.name,
        "inn": world.romashka.inn,
    }
    assert body["product"]["code"] == "UNSECURED"
    assert body["product"]["name"] == "Кредит без залога"
    assert body["request"]["amount"] == "3000000"
    assert body["info_request"]["comment"] == "Нужна выписка за 6 месяцев"
    assert [d["filename"] for d in body["documents"]] == ["statement.csv"]
    assert [e["title"] for e in body["timeline"]] == ["Заявка принята", "Нужна информация от вас"]
    assert body["decision"]["outcome"] == "REQUEST_INFO"
    assert body["decision"]["client_explanation"] == "Нужна выписка"
    assert len(body["feed"]) == 1
    assert body["available_actions"] == ["upload_document", "answer_info_request", "cancel"]


def test_card_status_comes_from_applications_not_the_projection(world: World) -> None:
    card = world.add_application(status="in_review", client_stage="Подбираем условия")
    # The client has just accepted the offer; the projection has not caught up.
    world.applications.add_card(
        replace(card, status="signing", offer=factories.offer("counter", "2000000"))
    )

    body = world.get(f"/bff/applications/{card.id}", world.as_client(world.director)).json()

    assert body["status"] == "signing"
    assert body["client_status"] == "signing"
    assert body["offer"]["kind"] == "counter"
    assert body["available_actions"] == ["sign"]


def test_card_offer_and_actions_by_rights(world: World) -> None:
    card = world.add_application(status="offer_ready", offer=factories.offer("counter", "2000000"))

    director = world.get(f"/bff/applications/{card.id}", world.as_client(world.director)).json()
    employee = world.get(f"/bff/applications/{card.id}", world.as_client(world.employee)).json()

    assert director["client_status"] == "counter_offer"
    assert director["offer"]["amount"] == "2000000"
    assert director["available_actions"] == ["accept_offer", "decline_offer", "cancel"]
    assert employee["available_actions"] == []
    assert employee["my_permissions"] == ["view"]


def test_only_a_signer_can_sign(world: World) -> None:
    card = world.add_application(status="signing", offer=factories.offer())

    director = world.get(f"/bff/applications/{card.id}", world.as_client(world.director)).json()
    accountant = world.get(f"/bff/applications/{card.id}", world.as_client(world.accountant)).json()

    assert director["available_actions"] == ["sign"]
    assert accountant["available_actions"] == []


def test_card_of_a_foreign_company_is_404(world: World) -> None:
    card = world.add_application(world.vector, status="in_review")

    foreign = world.get(f"/bff/applications/{card.id}", world.as_client(world.director))
    unknown = world.get(f"/bff/applications/{uuid4()}", world.as_client(world.director))
    # Bank staff use the back office card, not the client one.
    underwriter = world.get(f"/bff/applications/{card.id}", world.as_underwriter())

    assert foreign.status_code == 404
    assert foreign.json()["code"] == "not_found"
    assert unknown.status_code == 404
    assert underwriter.status_code == 404


# --- product matching ---------------------------------------------------------


def test_recommendations_for_a_company(world: World) -> None:
    world.decision.set_pre_approved(world.romashka.id, [factories.pre_approved("UNSECURED")])

    response = world.get(
        "/bff/products/recommend",
        world.as_client(world.director),
        organization_id=world.romashka.id,
        purpose="working_capital",
        amount="1000000",
        term_months=12,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(i["product_code"], i["fit"]) for i in items] == [
        ("UNSECURED", "best"),
        ("OVERDRAFT", "suitable"),
    ]
    assert items[0]["pre_approved_max"] == "4000000"
    assert items[1]["pre_approved_max"] is None
    assert Decimal(items[0]["payment_from"]) > 0


def test_recommendations_mark_unavailable_products(world: World) -> None:
    original = world.products.recommend

    async def recommend(*args: object, **kwargs: object) -> list:  # type: ignore[type-arg]
        found = await original(*args, **kwargs)  # type: ignore[arg-type]
        return [replace(found[0], eligible=False), *found[1:]]

    world.products.recommend = recommend  # type: ignore[method-assign]

    items = world.get(
        "/bff/products/recommend",
        world.as_client(world.director),
        organization_id=world.romashka.id,
        purpose="working_capital",
        amount="1000000",
        term_months=12,
    ).json()["items"]

    assert [(i["product_code"], i["fit"]) for i in items] == [
        ("UNSECURED", "unavailable"),
        ("OVERDRAFT", "best"),
    ]


def test_recommendations_without_a_company(world: World) -> None:
    items = world.get(
        "/bff/products/recommend",
        world.as_client(world.newcomer),
        purpose="working_capital",
        amount="1000000",
        term_months=12,
    ).json()["items"]

    assert {i["eligible"] for i in items} == {None}


def test_recommendations_for_a_foreign_company_is_404(world: World) -> None:
    response = world.get(
        "/bff/products/recommend",
        world.as_client(world.director),
        organization_id=world.vector.id,
        purpose="working_capital",
        amount="1000000",
        term_months=12,
    )

    assert response.status_code == 404
