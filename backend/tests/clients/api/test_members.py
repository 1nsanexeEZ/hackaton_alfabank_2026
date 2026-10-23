from datetime import timedelta
from uuid import uuid4

import pytest

from src.core.exceptions.exceptions import PermissionDeniedError
from src.core.messaging import topics
from src.modules.clients.facade import OrgPermission
from tests.clients.api.conftest import IVANOV, KUZNETSOVA, NOW, PETROV, SMIRNOVA, Demo


def members_url(demo: Demo, code: str, account_id: object = None, suffix: str = "") -> str:
    url = f"/organizations/{demo.orgs[code]}/members"
    return f"{url}/{account_id}{suffix}" if account_id is not None else url


def poa_body(valid_until: str = "2027-10-21", scope: list[str] | None = None) -> dict:
    return {
        "number": "77 АА 1234567",
        "issued_at": "2026-10-01",
        "valid_until": valid_until,
        "scope": scope or ["sign"],
    }


def test_members_with_names_and_rights(demo: Demo) -> None:
    body = demo.client.get(members_url(demo, "romashka"), headers=demo.as_client(KUZNETSOVA))
    assert body.status_code == 200
    members = {m["account_id"]: m for m in body.json()}
    director = members[str(demo.id_of(SMIRNOVA))]
    accountant = members[str(demo.id_of(KUZNETSOVA))]
    assert (director["role"], director["authority"]) == ("director", "registry")
    assert (director["last_name"], director["middle_name"]) == ("Смирнова", "Сергеевна")
    assert "sign" in director["permissions"]
    assert (accountant["role"], accountant["authority"]) == ("accountant", "unconfirmed")
    assert accountant["permissions"] == ["view", "submit_application", "edit_financials"]
    assert accountant["power_of_attorney"] is None


def test_director_adds_an_existing_account_by_phone(demo: Demo) -> None:
    newcomer = demo.identity.add_account(
        phone="+79995550011", last_name="Новикова", first_name="Нина"
    )
    response = demo.client.post(
        members_url(demo, "romashka"),
        json={"login": "8 (999) 555-00-11", "role": "employee"},
        headers=demo.as_client(SMIRNOVA),
    )
    assert response.status_code == 201, response.text
    member = response.json()
    assert member["account_id"] == str(newcomer.id)
    assert (member["role"], member["authority"]) == ("employee", "unconfirmed")
    assert member["permissions"] == ["view"] and member["last_name"] == "Новикова"

    [record] = demo.outbox()
    assert record.topic == topics.CLIENTS_EVENTS and record.message_type == "MemberAdded"
    assert record.key == str(demo.orgs["romashka"])
    payload = record.envelope["payload"]
    assert payload == {
        "organization_id": str(demo.orgs["romashka"]),
        "account_id": str(newcomer.id),
        "role": "employee",
    }
    assert record.envelope["producer"] == "clients"

    # The org_member port sees the new member at once.
    org_id = str(demo.orgs["romashka"])
    token = demo.headers(
        ["organizations.read"], {"organizations.read": ["org_member"]}, newcomer.id
    )
    assert [o["id"] for o in demo.client.get("/organizations", headers=token).json()] == [org_id]


def test_head_by_the_registry_is_recognised_by_name(demo: Demo) -> None:
    """Sidorov, the real head of Vector, joins: his authority is confirmed."""
    from dataclasses import replace

    sidorov = demo.identity.add_account(
        email="sidorov@vector.test", last_name="Сидоров", first_name="Сергей"
    )
    demo.identity.accounts[sidorov.id] = replace(sidorov, middle_name="Сергеевич")
    response = demo.client.post(
        members_url(demo, "vector"),
        json={"login": "sidorov@vector.test", "role": "director"},
        headers=demo.as_client(PETROV),
    )
    assert response.status_code == 201
    assert response.json()["authority"] == "registry"
    assert "sign" in response.json()["permissions"]


def test_unknown_login_and_duplicates(demo: Demo) -> None:
    headers = demo.as_client(SMIRNOVA)
    unknown = demo.client.post(
        members_url(demo, "romashka"),
        json={"login": "nobody@x.test", "role": "employee"},
        headers=headers,
    )
    assert unknown.status_code == 422
    assert unknown.json()["details"] == {"field": "login", "code": "account_not_found"}

    duplicate = demo.client.post(
        members_url(demo, "romashka"),
        json={"login": KUZNETSOVA, "role": "employee"},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["details"]["code"] == "already_member"
    assert demo.outbox() == []


def test_only_managers_change_members(demo: Demo) -> None:
    body = {"login": IVANOV, "role": "employee"}
    accountant = demo.client.post(
        members_url(demo, "romashka"), json=body, headers=demo.as_client(KUZNETSOVA)
    )
    assert accountant.status_code == 403
    assert accountant.json()["details"]["permission"] == "manage_members"
    # Somebody else's company stays hidden.
    stranger = demo.client.post(
        members_url(demo, "romashka"), json=body, headers=demo.as_client(PETROV)
    )
    assert stranger.status_code == 404
    for method, suffix, json in (("PATCH", "", {"role": "employee"}), ("DELETE", "", None)):
        response = demo.client.request(
            method,
            members_url(demo, "romashka", demo.id_of(SMIRNOVA), suffix),
            json=json,
            headers=demo.as_client(KUZNETSOVA),
        )
        assert response.status_code == 403, method


def test_change_role_and_remove(demo: Demo) -> None:
    headers = demo.as_client(SMIRNOVA)
    accountant = demo.id_of(KUZNETSOVA)
    changed = demo.client.patch(
        members_url(demo, "romashka", accountant), json={"role": "employee"}, headers=headers
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "employee" and changed.json()["permissions"] == ["view"]

    removed = demo.client.delete(members_url(demo, "romashka", accountant), headers=headers)
    assert removed.status_code == 204
    org_id = demo.orgs["romashka"]
    kuznetsova = demo.as_client(KUZNETSOVA)
    assert demo.client.get(f"/organizations/{org_id}", headers=kuznetsova).status_code == 404
    # Still the accountant of Ivanov.
    assert len(demo.client.get("/organizations", headers=kuznetsova).json()) == 1

    events = [(r.message_type, r.envelope["payload"]) for r in demo.outbox()]
    assert events == [
        (
            "MemberRoleChanged",
            {"organization_id": str(org_id), "account_id": str(accountant), "role": "employee"},
        ),
        ("MemberRemoved", {"organization_id": str(org_id), "account_id": str(accountant)}),
    ]
    missing = demo.client.delete(members_url(demo, "romashka", uuid4()), headers=headers)
    assert missing.status_code == 404


def test_last_manager_stays(demo: Demo) -> None:
    headers = demo.as_client(SMIRNOVA)
    me = demo.id_of(SMIRNOVA)
    for response in (
        demo.client.delete(members_url(demo, "romashka", me), headers=headers),
        demo.client.patch(
            members_url(demo, "romashka", me), json={"role": "employee"}, headers=headers
        ),
    ):
        assert response.status_code == 409
        assert response.json()["details"]["code"] == "last_manager"


def test_entrepreneur_has_no_director(demo: Demo) -> None:
    response = demo.client.post(
        members_url(demo, "ivanov"),
        json={"login": SMIRNOVA, "role": "director"},
        headers=demo.as_client(IVANOV),
    )
    assert response.status_code == 422
    assert response.json()["details"] == {"field": "role", "code": "not_allowed"}


def test_power_of_attorney_lets_the_accountant_sign_until_it_expires(demo: Demo) -> None:
    org_id = demo.orgs["romashka"]
    accountant = demo.id_of(KUZNETSOVA)

    async def ensure_sign(facade):  # type: ignore[no-untyped-def]
        await facade.ensure_can(accountant, org_id, OrgPermission.SIGN)

    with pytest.raises(PermissionDeniedError):
        demo.facade_call(ensure_sign)

    response = demo.client.post(
        members_url(demo, "romashka", accountant, "/poa"),
        json=poa_body(valid_until="2026-11-30"),
        headers=demo.as_client(SMIRNOVA),
    )
    assert response.status_code == 200, response.text
    member = response.json()
    assert member["authority"] == "power_of_attorney"
    assert member["power_of_attorney"]["is_valid"] is True
    assert member["power_of_attorney"]["scope"] == ["sign"]
    assert "sign" in member["permissions"]
    demo.facade_call(ensure_sign)

    demo.clock.set(NOW + timedelta(days=41))  # 2026-12-01
    with pytest.raises(PermissionDeniedError):
        demo.facade_call(ensure_sign)
    listed = demo.client.get(members_url(demo, "romashka"), headers=demo.as_client(SMIRNOVA))
    accountant_row = next(m for m in listed.json() if m["account_id"] == str(accountant))
    assert accountant_row["power_of_attorney"]["is_valid"] is False
    assert "sign" not in accountant_row["permissions"]


def test_power_of_attorney_rules(demo: Demo) -> None:
    petrov = demo.id_of(PETROV)
    # An unconfirmed director cannot empower himself.
    own = demo.client.post(
        members_url(demo, "vector", petrov, "/poa"), json=poa_body(), headers=demo.as_client(PETROV)
    )
    assert own.status_code == 403
    assert own.json()["details"]["code"] == "cannot_issue_power_of_attorney"

    headers = demo.as_client(SMIRNOVA)
    url = members_url(demo, "romashka", demo.id_of(KUZNETSOVA), "/poa")
    expired = demo.client.post(url, json=poa_body(valid_until="2026-10-20"), headers=headers)
    assert expired.status_code == 422 and expired.json()["details"]["code"] == "expired"
    not_delegable = demo.client.post(url, json=poa_body(scope=["manage_members"]), headers=headers)
    assert not_delegable.status_code == 422


def test_admin_acts_for_the_bank(demo: Demo) -> None:
    response = demo.client.post(
        members_url(demo, "vector"),
        json={"login": KUZNETSOVA, "role": "accountant"},
        headers=demo.as_admin(),
    )
    assert response.status_code == 201
    assert response.json()["role"] == "accountant"
