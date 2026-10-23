"""Calculator with the pre-approval: the rate is the bank's, a request above the
pre-approved terms gets a reason and a suggestion, not an error."""

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from src.core.access.permissions import Permissions
from src.core.exceptions.exceptions import InfrastructureError
from src.modules.decision.facade import DecisionFacade, PreApprovedOfferDTO
from src.modules.products.facade import EligibilityCheckDTO, EligibilityReasonDTO
from tests.bff import factories
from tests.bff.conftest import World


def calculate(
    world: World,
    organization_id: UUID | None = None,
    headers: dict[str, str] | None = None,
    code: str = "UNSECURED",
    **body: Any,
) -> httpx.Response:
    body.setdefault("amount", "3000000")
    body.setdefault("term_months", 24)
    return world.client.post(
        f"/bff/products/{code}/calculate",
        headers=world.as_client(world.director) if headers is None else headers,
        params={"organization_id": str(organization_id or world.romashka.id)},
        json=body,
    )


def pre_approve(world: World, **overrides: Any) -> PreApprovedOfferDTO:
    offer = replace(factories.pre_approved("UNSECURED", "4000000"), **overrides)
    world.decision.set_pre_approved(world.romashka.id, [offer])
    return offer


def monthly_payment(world: World, amount: str, term_months: int, rate: str) -> str:
    schedule = world.products.calculate_payment(
        Decimal(amount), term_months, Decimal(rate), "annuity"
    )
    return str(schedule.monthly_payment)


# --- the pre-approval ---------------------------------------------------------


def test_without_a_pre_approval_the_base_rate_is_used(world: World) -> None:
    response = calculate(world)

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body["schedule"]["rate"]) == Decimal("21.5")
    assert body["schedule"]["amount"] == "3000000"
    assert body["schedule"]["monthly_payment"] == monthly_payment(world, "3000000", 24, "21.5")
    assert len(body["schedule"]["payments"]) == 24
    assert body["pre_approved"] is None
    assert body["within_pre_approved"] is None
    assert body["eligible"] is True
    assert body["reasons"] == []
    assert body["suggestion"] is None
    assert body["degraded"] == []


def test_within_the_pre_approved_terms(world: World) -> None:
    pre_approve(world)

    body = calculate(world, amount="3000000", term_months=24).json()

    assert Decimal(body["schedule"]["rate"]) == Decimal("18.5")
    assert body["schedule"]["monthly_payment"] == monthly_payment(world, "3000000", 24, "18.5")
    assert body["pre_approved"] == {
        "max_amount": "4000000",
        "rate_from": "18.5",
        "term_max_months": 36,
        "valid_until": "2026-12-31",
        "basis": "estimate",
    }
    assert body["within_pre_approved"] is True
    assert body["reasons"] == []
    assert body["suggestion"] is None


def test_amount_above_the_pre_approved(world: World) -> None:
    pre_approve(world)

    response = calculate(world, amount="5000000", term_months=24)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schedule"]["amount"] == "5000000"
    assert Decimal(body["schedule"]["rate"]) == Decimal("18.5")
    assert body["within_pre_approved"] is False
    assert body["eligible"] is True
    assert body["reasons"] == [
        {
            "code": "amount_above_pre_approved",
            "passed": False,
            "message": "Предварительно доступно до 4 000 000 ₽",
        }
    ]
    assert body["suggestion"] == {
        "amount": "4000000",
        "term_months": 24,
        "monthly_payment": monthly_payment(world, "4000000", 24, "18.5"),
    }


def test_term_above_the_pre_approved(world: World) -> None:
    pre_approve(world, term_max_months=12)

    body = calculate(world, amount="3000000", term_months=24).json()

    assert body["schedule"]["term_months"] == 24
    assert body["within_pre_approved"] is False
    assert body["reasons"] == [
        {
            "code": "term_above_pre_approved",
            "passed": False,
            "message": "Предварительно доступен срок до 12 мес.",
        }
    ]
    assert body["suggestion"] == {
        "amount": "3000000",
        "term_months": 12,
        "monthly_payment": monthly_payment(world, "3000000", 12, "18.5"),
    }


def test_amount_and_term_above_the_pre_approved(world: World) -> None:
    pre_approve(world, term_max_months=12)

    body = calculate(world, amount="5000000", term_months=24).json()

    assert [r["code"] for r in body["reasons"]] == [
        "amount_above_pre_approved",
        "term_above_pre_approved",
    ]
    assert body["suggestion"]["amount"] == "4000000"
    assert body["suggestion"]["term_months"] == 12


def test_no_suggestion_below_the_product_minimum(world: World) -> None:
    pre_approve(world, max_amount=Decimal("50000"))

    body = calculate(world, amount="3000000").json()

    assert body["within_pre_approved"] is False
    assert [r["code"] for r in body["reasons"]] == ["amount_above_pre_approved"]
    assert body["suggestion"] is None


def test_a_pre_approval_of_another_product_is_not_used(world: World) -> None:
    world.decision.set_pre_approved(world.romashka.id, [factories.pre_approved("OVERDRAFT")])

    body = calculate(world).json()

    assert body["pre_approved"] is None
    assert body["within_pre_approved"] is None
    assert Decimal(body["schedule"]["rate"]) == Decimal("21.5")


# --- eligibility --------------------------------------------------------------


def test_a_company_that_does_not_fit_still_gets_the_schedule(world: World) -> None:
    world.products.set_eligibility(
        EligibilityCheckDTO(
            "UNSECURED",
            world.romashka.id,
            eligible=False,
            reasons=(
                EligibilityReasonDTO("legal_form", True, "ООО подходит"),
                EligibilityReasonDTO("business_age", False, "Бизнесу меньше 6 месяцев"),
            ),
        )
    )

    response = calculate(world)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eligible"] is False
    assert body["reasons"] == [
        {"code": "legal_form", "passed": True, "message": "ООО подходит"},
        {"code": "business_age", "passed": False, "message": "Бизнесу меньше 6 месяцев"},
    ]
    assert body["schedule"]["monthly_payment"] == monthly_payment(world, "3000000", 24, "21.5")


# --- decision did not answer --------------------------------------------------


def test_without_decision_the_schedule_is_at_the_base_rate(
    make_world: Callable[..., World],
) -> None:
    world = make_world(skip=(DecisionFacade,))

    response = calculate(world, amount="5000000")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] == ["pre_approved"]
    assert body["pre_approved"] is None
    assert body["within_pre_approved"] is None
    assert body["suggestion"] is None
    assert Decimal(body["schedule"]["rate"]) == Decimal("21.5")


def test_decision_that_is_down_degrades_the_pre_approval(world: World) -> None:
    async def broken(organization_id: UUID) -> list[PreApprovedOfferDTO]:
        raise InfrastructureError("decision database is unavailable")

    world.decision.get_pre_approved = broken  # type: ignore[method-assign]

    body = calculate(world).json()

    assert body["degraded"] == ["pre_approved"]
    assert body["pre_approved"] is None
    assert Decimal(body["schedule"]["rate"]) == Decimal("21.5")


# --- request ------------------------------------------------------------------


def test_the_default_schedule_of_the_product(world: World) -> None:
    default = calculate(world).json()
    differentiated = calculate(world, repayment="differentiated").json()

    assert default["schedule"]["repayment"] == "annuity"
    assert differentiated["schedule"]["repayment"] == "differentiated"


@pytest.mark.parametrize(
    "body,field,code",
    [
        ({"amount": "6000000"}, "amount", "out_of_range"),
        ({"amount": "50000"}, "amount", "out_of_range"),
        ({"term_months": 48}, "term_months", "out_of_range"),
        ({"term_months": 2}, "term_months", "out_of_range"),
        ({"repayment": "interest_only"}, "repayment", "not_offered"),
    ],
)
def test_the_product_frames_are_kept(
    world: World, body: dict[str, Any], field: str, code: str
) -> None:
    pre_approve(world)

    response = calculate(world, **body)

    assert response.status_code == 422
    assert response.json()["details"]["field"] == field
    assert response.json()["details"]["code"] == code


def test_the_rate_is_not_taken_from_the_client(world: World) -> None:
    response = calculate(world, rate="5")

    assert response.status_code == 422


def test_unknown_product_is_404(world: World) -> None:
    assert calculate(world, code="NO_SUCH_PRODUCT").status_code == 404


# --- access -------------------------------------------------------------------


def test_a_foreign_company_is_404(world: World) -> None:
    world.decision.set_pre_approved(world.vector.id, [factories.pre_approved("UNSECURED")])

    assert calculate(world, world.vector.id).status_code == 404
    assert calculate(world, uuid4()).status_code == 404
    newcomer = world.as_client(world.newcomer)
    assert calculate(world, world.romashka.id, newcomer).status_code == 404


def test_needs_credits_read(world: World) -> None:
    headers = world.token("client", world.director, without=(Permissions.CREDITS_READ,))

    assert calculate(world, headers=headers).status_code == 403
    response = world.client.post(
        "/bff/products/UNSECURED/calculate",
        params={"organization_id": str(world.romashka.id)},
        json={"amount": "3000000", "term_months": 24},
    )
    assert response.status_code == 401
