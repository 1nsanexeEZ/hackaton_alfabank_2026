from uuid import uuid4

from src.core.access.permissions import Permissions
from tests.clients.api.conftest import KUZNETSOVA, PETROV, SMIRNOVA, Demo

HEAD = ["view", "submit_application", "sign", "manage_members", "edit_financials"]
ACCOUNTANT = ["view", "submit_application", "edit_financials"]


def test_director_sees_her_company_only(demo: Demo) -> None:
    response = demo.client.get("/organizations", headers=demo.as_client(SMIRNOVA))
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(demo.orgs["romashka"]),
            "name": "ООО «Ромашка»",
            "inn": "7701158817",
            "legal_form": "LLC",
            "registry_status": "active",
            "my_role": "director",
            "my_permissions": HEAD,
        }
    ]


def test_accountant_sees_both_companies(demo: Demo) -> None:
    body = demo.client.get("/organizations", headers=demo.as_client(KUZNETSOVA)).json()
    assert [(o["inn"], o["legal_form"], o["my_role"], o["my_permissions"]) for o in body] == [
        ("770669871605", "IE", "accountant", ACCOUNTANT),
        ("7701158817", "LLC", "accountant", ACCOUNTANT),
    ]


def test_unconfirmed_director_cannot_sign(demo: Demo) -> None:
    body = demo.client.get("/organizations", headers=demo.as_client(PETROV)).json()
    assert len(body) == 1 and body[0]["my_role"] == "director"
    assert "sign" not in body[0]["my_permissions"]
    assert "manage_members" in body[0]["my_permissions"]


def test_somebody_elses_company_is_not_found(demo: Demo) -> None:
    headers = demo.as_client(SMIRNOVA)
    for org_id in (demo.orgs["vector"], uuid4()):
        for path in ("", "/members", "/financial-reports"):
            response = demo.client.get(f"/organizations/{org_id}{path}", headers=headers)
            assert response.status_code == 404, path
            assert response.json()["code"] == "not_found"


def test_card_of_the_company(demo: Demo) -> None:
    org_id = demo.orgs["romashka"]
    card = demo.client.get(f"/organizations/{org_id}", headers=demo.as_client(KUZNETSOVA)).json()
    assert card["ogrn"] == "1027700399869" and card["kpp"] == "770101001"
    assert card["business_age_months"] == 72
    assert card["registered_at"] == "2020-10-21"
    assert card["address"]["region_code"] == "77"
    assert card["okved_main"] == "56.10" and card["tax_regime"] == "osn"
    assert card["head_name"] == "Смирнова Анна Сергеевна"
    assert card["verification"]["status"] == "verified"
    assert card["verification"]["discrepancies"] == []
    assert card["my_role"] == "accountant" and card["my_permissions"] == ACCOUNTANT


def test_entrepreneur_card(demo: Demo) -> None:
    org_id = demo.orgs["ivanov"]
    card = demo.client.get(f"/organizations/{org_id}", headers=demo.as_client(KUZNETSOVA)).json()
    assert card["legal_form"] == "IE" and card["kpp"] is None
    assert card["tax_regime"] == "usn" and card["business_age_months"] == 8


def test_underwriter_sees_every_company(demo: Demo) -> None:
    headers = demo.as_underwriter()
    body = demo.client.get("/organizations", headers=headers).json()
    assert len(body) == 6
    assert {o["my_role"] for o in body} == {None}
    assert {o["registry_status"] for o in body} == {"active", "liquidating"}

    vector = demo.client.get(f"/organizations/{demo.orgs['vector']}", headers=headers).json()
    assert vector["my_permissions"] == []
    assert vector["head_name"] == "Сидоров Сергей Сергеевич"
    assert vector["verification"]["status"] == "mismatch"
    assert vector["verification"]["discrepancies"] == [
        {"field": "head_name", "declared": "Петров П. П.", "registry": "Сидоров С. С."}
    ]
    members = demo.client.get(f"/organizations/{demo.orgs['vector']}/members", headers=headers)
    assert members.status_code == 200 and len(members.json()) == 1


def test_permissions_are_required(demo: Demo) -> None:
    assert demo.client.get("/organizations").status_code == 401
    no_read = demo.headers([Permissions.FEED_READ], {})
    assert demo.client.get("/organizations", headers=no_read).status_code == 403
    # The underwriter reads but does not change companies.
    response = demo.client.post(
        f"/organizations/{demo.orgs['vector']}/members",
        json={"login": KUZNETSOVA, "role": "employee"},
        headers=demo.as_underwriter(),
    )
    assert response.status_code == 403


def test_client_without_memberships_sees_nothing(demo: Demo) -> None:
    newcomer = demo.identity.add_account(email="new@client.test")
    headers = demo.headers(
        [Permissions.ORGANIZATIONS_READ],
        {Permissions.ORGANIZATIONS_READ: ["org_member"]},
        newcomer.id,
    )
    assert demo.client.get("/organizations", headers=headers).json() == []
