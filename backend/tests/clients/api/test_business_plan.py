"""Business plan of a startup in the cabinet: one per company, revised in place, the financial
model by the template — 24 months, own funds, collateral, a state support guarantee, the loan."""

from decimal import Decimal
from typing import Any

from tests.clients.api.conftest import KUZNETSOVA, PETROV, SMIRNOVA, Demo


def plan_url(demo: Demo, code: str = "romashka") -> str:
    return f"/organizations/{demo.orgs[code]}/business-plan"


def plan(**model: Any) -> dict[str, Any]:
    return {
        "summary": "Кофейня у метро: зерно от обжарщика, завтраки, доставка по району",
        "financial_model": {
            "months": [{"revenue": "1000000", "expenses": "800000"}] * 24,
            "own_funds": "1000000",
            "collateral_value": "0",
            "guarantee": "msp_corporation",
            "guarantee_share": "0.5",
            "loan_amount": "3000000",
            "loan_term_months": 36,
            **model,
        },
    }


def test_the_plan_is_filled_in_then_revised(demo: Demo) -> None:
    headers = demo.as_client(SMIRNOVA)
    assert demo.client.get(plan_url(demo), headers=headers).status_code == 404

    created = demo.client.put(plan_url(demo), json=plan(), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["revision"] == 1 and body["submitted_by"] == str(demo.id_of(SMIRNOVA))
    model = body["financial_model"]
    assert len(model["months"]) == 24
    assert model["months"][0] == {"revenue": "1000000.00", "expenses": "800000.00"}
    assert model["guarantee"] == "msp_corporation" and Decimal(model["guarantee_share"]) == 1 / 2

    revised = demo.client.put(
        plan_url(demo),
        json=plan(loan_amount="2500000", collateral_value="900000"),
        headers=demo.as_client(KUZNETSOVA),
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["revision"] == 2
    read = demo.client.get(plan_url(demo), headers=headers).json()
    assert read["financial_model"]["loan_amount"] == "2500000.00"
    assert read["submitted_by"] == str(demo.id_of(KUZNETSOVA))

    async def business_plan(facade):  # type: ignore[no-untyped-def]
        return await facade.get_business_plan(demo.orgs["romashka"])

    found = demo.facade_call(business_plan)
    assert found.revision == 2 and found.financial_model.collateral_value == Decimal("900000")
    assert found.financial_model.months[23].expenses == Decimal("800000")
    # Ничего не публикуется: план оценивают по запросу клиента.
    assert demo.outbox() == []


def test_the_template_is_checked(demo: Demo) -> None:
    headers = demo.as_client(SMIRNOVA)
    cases = [
        plan(months=[{"revenue": "1", "expenses": "1"}] * 23),
        plan(own_funds="-1"),
        plan(loan_amount="0"),
        plan(guarantee_share="1.5"),
    ]
    for body in cases:
        response = demo.client.put(plan_url(demo), json=body, headers=headers)
        assert response.status_code == 422, response.text
    no_guarantee = demo.client.put(
        plan_url(demo), json=plan(guarantee="none", guarantee_share="0.3"), headers=headers
    )
    assert no_guarantee.status_code == 422
    assert no_guarantee.json()["details"]["code"] == "no_guarantee"
    blank = demo.client.put(plan_url(demo), json={**plan(), "summary": "   "}, headers=headers)
    assert blank.status_code == 422
    assert demo.client.get(plan_url(demo), headers=headers).status_code == 404


def test_only_members_with_edit_financials(demo: Demo) -> None:
    stranger = demo.client.put(plan_url(demo), json=plan(), headers=demo.as_client(PETROV))
    assert stranger.status_code == 404
    assert demo.client.get(plan_url(demo), headers=demo.as_client(PETROV)).status_code == 404
    underwriter = demo.client.put(plan_url(demo), json=plan(), headers=demo.as_underwriter())
    assert underwriter.status_code == 403

    employee = demo.identity.add_account(email="employee@romashka.test")
    added = demo.client.post(
        f"/organizations/{demo.orgs['romashka']}/members",
        json={"login": "employee@romashka.test", "role": "employee"},
        headers=demo.as_client(SMIRNOVA),
    )
    assert added.status_code == 201
    headers = demo.headers(
        ["organizations.read", "organizations.update"],
        {"organizations.read": ["org_member"], "organizations.update": ["org_member"]},
        employee.id,
    )
    response = demo.client.put(plan_url(demo), json=plan(), headers=headers)
    assert response.status_code == 403
    assert response.json()["details"]["permission"] == "edit_financials"

    filled = demo.client.put(plan_url(demo), json=plan(), headers=demo.as_client(SMIRNOVA))
    assert filled.status_code == 201
    # Сотрудник и банк читают план.
    assert demo.client.get(plan_url(demo), headers=headers).status_code == 200
    assert demo.client.get(plan_url(demo), headers=demo.as_underwriter()).status_code == 200
