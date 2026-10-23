"""Ветка стартапа в кабинете: сегмент компании на дашборде, предскрин учредителя, бизнес-план и
проектная оценка вместо предодобрения по оборотам, в подборе — только продукты для стартапа (и
наоборот); у андеррайтера — проектная оценка и заполненная по ней форма."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

from src.modules.clients.facade import (
    BusinessPlanDTO,
    FinancialModelDTO,
    OrganizationSnapshotDTO,
    PlanMonthDTO,
)
from src.modules.decision.facade import (
    FounderPrescreenDTO,
    PreApprovedOfferDTO,
    PrescreenReasonDTO,
    ProjectAssessmentDTO,
    ProjectCheckDTO,
    ProjectFiguresDTO,
)
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

    assert body["startup"] == {"prescreen": None, "business_plan_revision": None, "project": None}


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


def project(status: str = "passed", **overrides: Any) -> ProjectAssessmentDTO:
    passed = status == "passed"
    values: dict[str, Any] = {
        "status": status,
        "product_code": "STARTUP",
        "plan_revision": 1,
        "max_amount": Decimal("3810000") if passed else None,
        "checked_at": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=29),
        "valid": True,
        "reasons": (
            ProjectCheckDTO(
                "dscr",
                passed,
                "Денежного потока по финмодели хватает на платежи по кредиту с запасом"
                if passed
                else "Денежного потока по финмодели не хватает на платежи по кредиту с запасом",
            ),
        ),
        "figures": ProjectFiguresDTO(
            requested_amount=Decimal("3000000"),
            term_months=36,
            rate=Decimal("26"),
            cash_flow=Decimal("4800000"),
            debt_service=Decimal("2900924.64"),
            dscr=Decimal("1.65"),
            own_share=Decimal("0.25"),
            coverage=Decimal("0.5"),
            capacity=Decimal("3818411.03"),
        ),
        "version": "project_v1",
        **overrides,
    }
    return ProjectAssessmentDTO(**values)


def business_plan(company: OrganizationSnapshotDTO, revision: int = 1) -> BusinessPlanDTO:
    return BusinessPlanDTO(
        organization_id=company.id,
        summary="Кофейня у метро",
        financial_model=FinancialModelDTO(
            months=(PlanMonthDTO(Decimal("1000000"), Decimal("800000")),) * 24,
            own_funds=Decimal("1000000"),
            collateral_value=Decimal("0"),
            collateral_description="Поручительство учредителя",
            guarantee="msp_corporation",
            guarantee_share=Decimal("0.5"),
            loan_amount=Decimal("3000000"),
            loan_term_months=36,
        ),
        submitted_by=None,
        submitted_at=NOW - timedelta(days=2),
        revision=revision,
    )


def project_offer() -> PreApprovedOfferDTO:
    return PreApprovedOfferDTO(
        product_code="STARTUP",
        max_amount=Decimal("3810000"),
        rate_from=Decimal("15"),
        term_max_months=60,
        valid_until=(NOW + timedelta(days=29)).date(),
        basis="project",
    )


def test_startup_dashboard_shows_the_project_and_its_offer(world: World) -> None:
    company = add_startup(world)
    world.decision.set_prescreen(company.id, prescreen())
    world.clients.business_plans[company.id] = business_plan(company, revision=2)
    world.decision.set_project(company.id, project())
    world.decision.set_pre_approved(
        company.id, [project_offer(), factories.pre_approved("UNSECURED")]
    )

    body = world.get(
        "/bff/dashboard", world.as_client(world.petrov), organization_id=company.id
    ).json()

    # Только проектное: оборотов для предодобрения по оценке у стартапа нет.
    [offer] = body["pre_approved"]
    assert offer["product_code"] == "STARTUP" and offer["max_amount"] == "3810000"
    assert offer["product_name"] == "Кредит на запуск бизнеса"
    startup = body["startup"]
    assert startup["business_plan_revision"] == 2
    assert startup["project"]["status"] == "passed"
    assert startup["project"]["max_amount"] == "3810000"
    # План поменяли после оценки — фронт предложит оценить заново.
    assert startup["project"]["plan_revision"] == 1
    assert startup["project"]["reasons"][0]["code"] == "dscr"
    # Цифр модели клиент не видит: по ним угадываются пороги.
    assert "figures" not in startup["project"]


def calculate_startup(world: World, company: OrganizationSnapshotDTO, amount: str) -> Any:
    response = world.client.post(
        "/bff/products/STARTUP/calculate",
        headers=world.as_client(world.petrov),
        params={"organization_id": str(company.id)},
        json={"amount": amount, "term_months": 24},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_startup_calculator_is_capped_by_the_project_offer(world: World) -> None:
    company = add_startup(world)
    world.decision.set_pre_approved(company.id, [project_offer()])

    within = calculate_startup(world, company, "3000000")
    above = calculate_startup(world, company, "4500000")

    # Отчётности у стартапа нет: потолок — сумма проектной оценки, платёжеспособность не считаем.
    assert within["max_affordable"] == "3810000"
    assert within["affordable_by"] == "project"
    assert within["above_affordable"] is False
    assert within["pre_approved"]["basis"] == "estimate"
    assert above["max_affordable"] == "3810000"
    assert above["above_affordable"] is True
    assert [r["code"] for r in above["reasons"]] == ["amount_above_pre_approved"]
    assert above["suggestion"]["amount"] == "3810000"


def test_startup_calculator_without_a_project_offer(world: World) -> None:
    company = add_startup(world)

    body = calculate_startup(world, company, "3000000")

    assert body["pre_approved"] is None
    assert body["max_affordable"] is None
    assert body["above_affordable"] is False


def startup_card(world: World, amount: str) -> Any:
    company = add_startup(world)
    world.clients.business_plans[company.id] = business_plan(company)
    return world.add_application(
        company, amount=Decimal(amount), term_months=36, product_code="STARTUP"
    )


def test_underwriter_confirms_the_project_within_the_pre_approval(world: World) -> None:
    card = startup_card(world, "3000000")
    world.decision.set_project(card.organization_id, project())

    body = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter()).json()

    startup = body["startup"]
    assert startup["valid_at_submission"] and not startup["plan_changed"]
    assert startup["assessment"]["figures"]["dscr"] == "1.65"
    assert startup["business_plan"]["financial_model"]["own_funds"] == "1000000"
    assert startup["form"] == {
        "decision": "approve",
        "amount": "3000000",
        "term_months": 36,
        "business_plan": "acceptable",
        "collateral": "Поручительство учредителя; гарантия Корпорации МСП на 50% суммы",
        "support_program": True,
    }


def test_above_the_pre_approval_the_form_offers_less(world: World) -> None:
    card = startup_card(world, "4500000")
    world.decision.set_project(card.organization_id, project())

    form = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter()).json()[
        "startup"
    ]["form"]

    assert (form["decision"], form["amount"]) == ("counter_offer", "3810000")


def test_failed_or_expired_project_is_a_reject_to_confirm(world: World) -> None:
    card = startup_card(world, "3000000")
    world.decision.set_project(card.organization_id, project("failed"))
    failed = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter()).json()
    assert failed["startup"]["form"]["decision"] == "reject"
    assert failed["startup"]["form"]["business_plan"] == "weak"

    expired = project(
        checked_at=NOW - timedelta(days=40), valid_until=NOW - timedelta(days=10), valid=False
    )
    world.decision.set_project(card.organization_id, expired)
    body = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter()).json()
    assert not body["startup"]["valid_at_submission"]
    assert body["startup"]["form"]["decision"] == "reject"


def test_no_startup_block_for_other_products(world: World) -> None:
    card = world.add_application(status="in_review")
    world.decision.set_project(card.organization_id, replace(project(), product_code="STARTUP"))

    body = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter()).json()

    assert body["startup"] is None
