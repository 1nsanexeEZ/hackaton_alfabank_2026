from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from src.core.access.permissions import Permissions
from src.modules.projector.facade import OrganizationDashboardDTO
from tests.bff import factories
from tests.bff.conftest import World
from tests.fakes.builders import NOW


def test_newcomer_gets_onboarding(world: World) -> None:
    response = world.get("/bff/dashboard", world.as_client(world.newcomer))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["onboarding"] is True
    assert body["organization"] is None
    assert body["organizations"] == []
    assert body["active_applications"] == []


def test_dashboard_of_the_first_company(world: World) -> None:
    org = world.romashka
    world.projector.dashboards[org.id] = OrganizationDashboardDTO(
        organization_id=org.id,
        active_applications=4,
        action_required_count=3,
        pre_approved_max_amount=Decimal("4000000"),
        pre_approved_rate_from=Decimal("18.5"),
        last_activity_at=NOW,
    )
    info = world.add_application(status="info_requested", number="КР-1")
    offer = world.add_application(
        status="offer_ready", number="КР-2", offer=factories.offer("counter", "2000000")
    )
    sign = world.add_application(status="signing", number="КР-3")
    review = world.add_application(
        status="in_review", number="КР-4", client_stage="Оцениваем заявку"
    )
    world.add_application(status="rejected", number="КР-5")
    world.add_application(world.vector, status="in_review", number="КР-6")
    world.decision.set_pre_approved(org.id, [factories.pre_approved("UNSECURED")])
    world.notifications.add_item(world.director, factories.feed_item(org.id))
    world.notifications.add_item(world.director, factories.feed_item(org.id, read=True))
    world.notifications.add_item(world.director, factories.feed_item(world.vector.id))
    world.notifications.set_news(org.id, [factories.news_item()])

    response = world.get("/bff/dashboard", world.as_client(world.director))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["onboarding"] is False
    assert body["degraded"] == []
    assert body["organization"]["id"] == str(org.id)
    assert body["organization"]["verification_status"] == "verified"
    assert body["organization"]["my_role"] == "director"
    assert "sign" in body["organization"]["my_permissions"]
    assert [o["id"] for o in body["organizations"]] == [str(org.id)]
    assert body["counters"]["action_required_count"] == 3
    active = {row["number"]: row for row in body["active_applications"]}
    assert set(active) == {"КР-1", "КР-2", "КР-3", "КР-4"}
    assert active["КР-2"]["client_status"] == "counter_offer"
    assert active["КР-4"]["client_status"] == "scoring"
    assert {(t["application_id"], t["kind"]) for t in body["todo"]} == {
        (str(info.id), "info_requested"),
        (str(offer.id), "offer_ready"),
        (str(sign.id), "signing"),
    }
    assert str(review.id) not in {t["application_id"] for t in body["todo"]}
    assert body["pre_approved"] == [
        {
            "product_code": "UNSECURED",
            "product_name": "Кредит без залога",
            "max_amount": "4000000",
            "rate_from": "18.5",
            "term_max_months": 36,
            "valid_until": "2026-12-31",
        }
    ]
    assert body["feed"]["unread"] == 1
    assert len(body["feed"]["items"]) == 2
    assert [n["title"] for n in body["news"]] == ["Льготная ставка для общепита"]


def test_who_may_not_apply_sees_no_pre_approval_and_no_tasks(world: World) -> None:
    """An employee without a power of attorney (or whose one is revoked) only views."""
    org = world.romashka
    world.projector.dashboards[org.id] = OrganizationDashboardDTO(
        organization_id=org.id,
        active_applications=1,
        action_required_count=1,
        pre_approved_max_amount=Decimal("4000000"),
        pre_approved_rate_from=Decimal("18.5"),
        last_activity_at=NOW,
    )
    world.add_application(status="signing", number="КР-3")
    world.decision.set_pre_approved(org.id, [factories.pre_approved("UNSECURED")])

    response = world.get("/bff/dashboard", world.as_client(world.employee))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization"]["my_permissions"] == ["view"]
    assert body["pre_approved"] == []
    assert body["counters"]["pre_approved_max_amount"] is None
    assert body["counters"]["pre_approved_rate_from"] is None
    assert body["todo"] == []
    assert [a["number"] for a in body["active_applications"]] == ["КР-3"]


def test_dashboard_shows_at_most_five_active_applications(world: World) -> None:
    for minute in range(7):
        world.add_application(
            status="in_review",
            number=f"КР-{minute}",
            updated_at=NOW + timedelta(minutes=minute),
        )

    body = world.get("/bff/dashboard", world.as_client(world.director)).json()

    assert [row["number"] for row in body["active_applications"]] == [
        "КР-6",
        "КР-5",
        "КР-4",
        "КР-3",
        "КР-2",
    ]


def test_dashboard_switches_company(world: World) -> None:
    world.add_application(world.ivanov, status="draft", number="КР-ИП")

    response = world.get(
        "/bff/dashboard", world.as_client(world.accountant), organization_id=world.ivanov.id
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization"]["id"] == str(world.ivanov.id)
    assert body["organization"]["my_role"] == "accountant"
    assert {o["id"] for o in body["organizations"]} == {
        str(world.romashka.id),
        str(world.ivanov.id),
    }
    assert [row["number"] for row in body["active_applications"]] == ["КР-ИП"]


def test_dashboard_of_a_foreign_company_is_404(world: World) -> None:
    headers = world.as_client(world.director)

    assert world.get("/bff/dashboard", headers, organization_id=world.vector.id).status_code == 404
    assert world.get("/bff/dashboard", headers, organization_id=uuid4()).status_code == 404
    newcomer = world.as_client(world.newcomer)
    assert world.get("/bff/dashboard", newcomer, organization_id=world.vector.id).status_code == 404


def test_dashboard_needs_organizations_read(world: World) -> None:
    headers = world.token("client", world.director, without=(Permissions.ORGANIZATIONS_READ,))

    assert world.get("/bff/dashboard", headers).status_code == 403
    assert world.client.get("/bff/dashboard").status_code == 401
