"""Ветка стартапа в кабинете: сегмент компании на дашборде, предскрин учредителя вместо
предодобрения, в подборе — только продукты для стартапа (и наоборот)."""

from datetime import timedelta

from src.modules.clients.facade import OrganizationSnapshotDTO
from src.modules.decision.facade import FounderPrescreenDTO, PrescreenReasonDTO
from tests.bff import factories
from tests.bff.conftest import World
from tests.fakes import builders
from tests.fakes.builders import NOW


def add_startup(world: World) -> OrganizationSnapshotDTO:
    company = world.clients.add_organization(builders.organization_snapshot("start"))
    world.clients.add_member(world.petrov, company.id, "director")
    world.products.add_product(
        builders.product("STARTUP", name="Кредит на запуск бизнеса", startup_only=True)
    )
    return company


def prescreen(status: str = "passed") -> FounderPrescreenDTO:
    return FounderPrescreenDTO(
        status=status,  # type: ignore[arg-type]
        founder_account_id=builders.organization_snapshot("start").id,
        founder_name="Стартов Степан Сергеевич",
        checked_at=NOW,
        valid_until=NOW + timedelta(days=30),
        valid=True,
        reasons=(PrescreenReasonDTO("no_current_overdue", True, "Текущей просрочки нет"),),
    )


def test_startup_dashboard_shows_the_prescreen_instead_of_pre_approval(world: World) -> None:
    company = add_startup(world)
    world.decision.set_pre_approved(company.id, [factories.pre_approved("UNSECURED")])
    world.decision.set_prescreen(company.id, prescreen())

    body = world.get(
        "/bff/dashboard", world.as_client(world.petrov), organization_id=company.id
    ).json()

    assert body["organization"]["segment"] == "startup"
    assert body["pre_approved"] == []
    assert body["startup"]["prescreen"]["status"] == "passed"
    assert body["startup"]["prescreen"]["founder_name"] == "Стартов Степан Сергеевич"
    assert body["startup"]["prescreen"]["reasons"] == [
        {"code": "no_current_overdue", "passed": True, "message": "Текущей просрочки нет"}
    ]


def test_startup_without_a_prescreen_yet(world: World) -> None:
    company = add_startup(world)

    body = world.get(
        "/bff/dashboard", world.as_client(world.petrov), organization_id=company.id
    ).json()

    assert body["startup"] == {"prescreen": None}


def test_established_company_has_no_startup_block(world: World) -> None:
    body = world.get("/bff/dashboard", world.as_client(world.director)).json()

    assert body["organization"]["segment"] == "established"
    assert body["startup"] is None


def test_startup_is_matched_only_with_startup_products(world: World) -> None:
    company = add_startup(world)

    items = world.get(
        "/bff/products/recommend",
        world.as_client(world.petrov),
        organization_id=company.id,
        purpose="working_capital",
        amount="1000000",
        term_months=12,
    ).json()["items"]

    assert [i["product_code"] for i in items] == ["STARTUP"]


def test_established_company_is_not_offered_the_startup_product(world: World) -> None:
    add_startup(world)

    items = world.get(
        "/bff/products/recommend",
        world.as_client(world.director),
        organization_id=world.romashka.id,
        purpose="working_capital",
        amount="1000000",
        term_months=12,
    ).json()["items"]

    assert "STARTUP" not in [i["product_code"] for i in items]
    assert items
