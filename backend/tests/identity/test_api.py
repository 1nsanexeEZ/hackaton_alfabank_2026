from collections.abc import Callable

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, auth

Login = Callable[[str, str], str]
PASSWORD = "Client-password-1"


def create_role(client: TestClient, token: str, **body) -> dict:
    response = client.post("/roles", json=body, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def create_account(client: TestClient, token: str, role_id: str, **login) -> dict:
    body = {
        **login,
        "password": PASSWORD,
        "role_id": role_id,
        "profile": {"last_name": "Петрова", "first_name": "Анна"},
    }
    response = client.post("/accounts", json=body, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()


# --- auth ---------------------------------------------------------------------------------


def test_bootstrap_admin_logs_in(client: TestClient, admin_token: str) -> None:
    me = client.get("/me", headers=auth(admin_token)).json()
    assert me["email"] == ADMIN_EMAIL
    assert me["role"]["name"] == "admin"
    assert me["permissions"] == ["admin"]


@pytest.mark.parametrize("login_value", [ADMIN_EMAIL, "nobody@example.com", "+79990000000"])
def test_bad_credentials_look_the_same(client: TestClient, login_value: str) -> None:
    response = client.post("/auth/login", json={"login": login_value, "password": "wrong-pass"})
    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized", "message": "Invalid login or password"}


@pytest.mark.parametrize("headers", [{}, auth("not-a-jwt"), {"Authorization": "Basic abc"}])
def test_protected_routes_need_a_valid_token(client: TestClient, headers: dict) -> None:
    for path in ("/me", "/accounts", "/roles"):
        response = client.get(path, headers=headers)
        assert response.status_code == 401, path
        assert response.headers["WWW-Authenticate"] == "Bearer"


def test_token_verifies_with_jwks(client: TestClient, admin_token: str) -> None:
    """What another service would do: verify the token knowing only the JWKS."""
    jwks = client.get("/.well-known/jwks.json").json()
    kid = jwt.get_unverified_header(admin_token)["kid"]
    key = next(jwt.PyJWK(k) for k in jwks["keys"] if k["kid"] == kid)

    claims = jwt.decode(admin_token, key, algorithms=["RS256"], audience="credit-cabinet")

    assert claims["permissions"] == ["admin"]


def test_login_by_phone_in_any_format(client: TestClient, admin_token: str, login: Login) -> None:
    role = create_role(client, admin_token, name="client")
    account = create_account(client, admin_token, role["id"], phone="8 (999) 123-45-67")
    assert account["phone"] == "+79991234567"

    for value in ("+7 999 123 45 67", "89991234567", "79991234567"):
        assert login(value, PASSWORD)


def test_email_is_case_insensitive(client: TestClient, admin_token: str, login: Login) -> None:
    role = create_role(client, admin_token, name="client")
    create_account(client, admin_token, role["id"], email="Anna@Example.com")
    assert login("ANNA@example.com", PASSWORD)


# --- RBAC ---------------------------------------------------------------------------------


def test_permission_is_checked_on_the_route(
    client: TestClient, admin_token: str, login: Login
) -> None:
    reader = create_role(client, admin_token, name="reader", permissions=["accounts.read"])
    create_account(client, admin_token, reader["id"], email="reader@example.com")
    token = login("reader@example.com", PASSWORD)

    assert client.get("/accounts", headers=auth(token)).status_code == 200
    denied = client.post(
        "/accounts",
        json={
            "email": "x@example.com",
            "password": PASSWORD,
            "role_id": reader["id"],
            "profile": {"last_name": "X", "first_name": "Y"},
        },
        headers=auth(token),
    )
    assert denied.status_code == 403
    assert denied.json() == {
        "code": "permission_denied",
        "message": "Not enough rights: accounts.create",
    }
    assert client.get("/roles", headers=auth(token)).status_code == 403


def test_role_changes_apply_with_the_next_token(
    client: TestClient, admin_token: str, login: Login
) -> None:
    role = create_role(client, admin_token, name="client")
    create_account(client, admin_token, role["id"], email="anna@example.com")
    old_token = login("anna@example.com", PASSWORD)

    client.patch(
        f"/roles/{role['id']}", json={"permissions": ["accounts.read"]}, headers=auth(admin_token)
    )

    assert client.get("/accounts", headers=auth(old_token)).status_code == 403
    new_token = login("anna@example.com", PASSWORD)
    assert client.get("/accounts", headers=auth(new_token)).status_code == 200


# --- ABAC ---------------------------------------------------------------------------------


def test_not_deleted_policy_hides_deleted_accounts(
    client: TestClient, admin_token: str, login: Login
) -> None:
    manager = create_role(
        client,
        admin_token,
        name="manager",
        permissions=["accounts.read"],
        policies={"accounts.read": ["not_deleted"]},
    )
    create_account(client, admin_token, manager["id"], email="manager@example.com")
    victim = create_account(client, admin_token, manager["id"], email="victim@example.com")
    assert client.delete(f"/accounts/{victim['id']}", headers=auth(admin_token)).status_code == 204

    token = login("manager@example.com", PASSWORD)
    visible = {a["id"] for a in client.get("/accounts", headers=auth(token)).json()}
    assert victim["id"] not in visible
    assert client.get(f"/accounts/{victim['id']}", headers=auth(token)).status_code == 404

    # admin is never row-restricted and sees the deleted account with its deletion date
    seen_by_admin = client.get(f"/accounts/{victim['id']}", headers=auth(admin_token)).json()
    assert seen_by_admin["deleted_at"] is not None


def test_policy_on_a_model_without_support_fails_loud(
    client: TestClient, admin_token: str, login: Login
) -> None:
    """Accounts have no owner_id, so `own_only` can't be enforced on them:
    better a 500 than silently returning every row."""
    broken = create_role(
        client,
        admin_token,
        name="broken",
        permissions=["accounts.read"],
        policies={"accounts.read": ["own_only"]},
    )
    create_account(client, admin_token, broken["id"], email="broken@example.com")
    token = login("broken@example.com", PASSWORD)

    with pytest.raises(ValueError, match="does not support policy 'own_only'"):
        client.get("/accounts", headers=auth(token))


def test_policies_must_belong_to_granted_permissions(client: TestClient, admin_token: str) -> None:
    response = client.post(
        "/roles",
        json={"name": "bad", "permissions": [], "policies": {"requests.read": ["own_only"]}},
        headers=auth(admin_token),
    )
    assert response.status_code == 400
    assert "requests.read" in response.json()["message"]


def test_unknown_permission_is_rejected(client: TestClient, admin_token: str) -> None:
    response = client.post(
        "/roles", json={"name": "bad", "permissions": ["rockets.launch"]}, headers=auth(admin_token)
    )
    assert response.status_code == 422


# --- accounts -----------------------------------------------------------------------------


def test_deleted_account_cannot_log_in_and_frees_its_email(
    client: TestClient, admin_token: str
) -> None:
    role = create_role(client, admin_token, name="client")
    account = create_account(client, admin_token, role["id"], email="anna@example.com")
    client.delete(f"/accounts/{account['id']}", headers=auth(admin_token))

    response = client.post("/auth/login", json={"login": "anna@example.com", "password": PASSWORD})
    assert response.status_code == 401
    create_account(client, admin_token, role["id"], email="anna@example.com")


def test_login_must_be_unique(client: TestClient, admin_token: str) -> None:
    role = create_role(client, admin_token, name="client")
    create_account(client, admin_token, role["id"], email="anna@example.com")
    response = client.post(
        "/accounts",
        json={
            "email": "anna@example.com",
            "password": PASSWORD,
            "role_id": role["id"],
            "profile": {"last_name": "X", "first_name": "Y"},
        },
        headers=auth(admin_token),
    )
    assert response.status_code == 409


def test_account_needs_email_or_phone(client: TestClient, admin_token: str) -> None:
    role = create_role(client, admin_token, name="client")
    response = client.post(
        "/accounts",
        json={
            "password": PASSWORD,
            "role_id": role["id"],
            "profile": {"last_name": "X", "first_name": "Y"},
        },
        headers=auth(admin_token),
    )
    assert response.status_code == 422


def test_update_account(client: TestClient, admin_token: str, login: Login) -> None:
    role = create_role(client, admin_token, name="client")
    account = create_account(client, admin_token, role["id"], email="anna@example.com")

    response = client.patch(
        f"/accounts/{account['id']}",
        json={
            "phone": "+79991112233",
            "password": "New-password-1",
            "profile": {"position": "Финансовый директор"},
        },
        headers=auth(admin_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["phone"] == "+79991112233"
    assert response.json()["profile"]["position"] == "Финансовый директор"
    assert login("+79991112233", "New-password-1")


def test_admin_cannot_delete_itself(client: TestClient, admin_token: str) -> None:
    me = client.get("/me", headers=auth(admin_token)).json()
    assert client.delete(f"/accounts/{me['id']}", headers=auth(admin_token)).status_code == 400


def test_role_in_use_cannot_be_deleted(client: TestClient, admin_token: str) -> None:
    role = create_role(client, admin_token, name="client")
    create_account(client, admin_token, role["id"], email="anna@example.com")
    assert client.delete(f"/roles/{role['id']}", headers=auth(admin_token)).status_code == 409

    unused = create_role(client, admin_token, name="unused")
    assert client.delete(f"/roles/{unused['id']}", headers=auth(admin_token)).status_code == 204


# --- me -----------------------------------------------------------------------------------


def test_profile_update_needs_permission(
    client: TestClient, admin_token: str, login: Login
) -> None:
    plain = create_role(client, admin_token, name="plain")
    editor = create_role(client, admin_token, name="editor", permissions=["profile.update"])
    create_account(client, admin_token, plain["id"], email="plain@example.com")
    create_account(client, admin_token, editor["id"], email="editor@example.com")
    body = {"position": "Финансовый директор"}

    plain_token = login("plain@example.com", PASSWORD)
    assert client.patch("/me/profile", json=body, headers=auth(plain_token)).status_code == 403

    editor_token = login("editor@example.com", PASSWORD)
    response = client.patch("/me/profile", json=body, headers=auth(editor_token))
    assert response.status_code == 200
    assert response.json()["profile"]["position"] == "Финансовый директор"


def test_name_is_locked_without_update_name(
    client: TestClient, admin_token: str, login: Login
) -> None:
    """A client's name is confirmed by the bank: `profile.update` alone keeps it."""
    client_role = create_role(client, admin_token, name="client", permissions=["profile.update"])
    create_account(client, admin_token, client_role["id"], email="anna@example.com")
    token = login("anna@example.com", PASSWORD)

    response = client.patch(
        "/me/profile",
        json={"last_name": "Иванова", "first_name": "Анна", "position": "Директор"},
        headers=auth(token),
    )
    assert response.status_code == 422
    assert response.json()["details"] == {"code": "identity_locked", "fields": ["last_name"]}
    me = client.get("/me", headers=auth(token)).json()
    assert me["profile"]["last_name"] == "Петрова"
    assert me["profile"]["position"] is None


def test_same_name_with_position_passes(client: TestClient, admin_token: str, login: Login) -> None:
    """The form sends every field: the unchanged name doesn't block the position."""
    client_role = create_role(client, admin_token, name="client", permissions=["profile.update"])
    create_account(client, admin_token, client_role["id"], email="anna@example.com")
    token = login("anna@example.com", PASSWORD)

    response = client.patch(
        "/me/profile",
        json={"last_name": "Петрова", "first_name": "Анна", "position": "Директор"},
        headers=auth(token),
    )
    assert response.status_code == 200
    assert response.json()["profile"]["position"] == "Директор"


def test_staff_change_their_own_name(client: TestClient, admin_token: str, login: Login) -> None:
    staff = create_role(
        client,
        admin_token,
        name="underwriter",
        permissions=["profile.update", "profile.update_name"],
    )
    create_account(client, admin_token, staff["id"], email="staff@example.com")
    token = login("staff@example.com", PASSWORD)

    response = client.patch("/me/profile", json={"middle_name": "Сергеевна"}, headers=auth(token))
    assert response.status_code == 200
    assert response.json()["profile"]["middle_name"] == "Сергеевна"


def test_admin_corrects_a_clients_name(client: TestClient, admin_token: str) -> None:
    """A new passport: the bank's staff change the name, the client can't."""
    client_role = create_role(client, admin_token, name="client", permissions=["profile.update"])
    account = create_account(client, admin_token, client_role["id"], email="anna@example.com")

    response = client.patch(
        f"/accounts/{account['id']}",
        json={"profile": {"last_name": "Иванова", "first_name": "Анна"}},
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["profile"]["last_name"] == "Иванова"


def test_bootstrap_is_idempotent(client: TestClient, settings, login: Login) -> None:
    from src.main import create_app

    with TestClient(create_app(settings)):
        pass
    assert login(ADMIN_EMAIL, ADMIN_PASSWORD)
