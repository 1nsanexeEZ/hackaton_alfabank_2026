"""Demo accounts seeded on startup (SEED_DEMO_DATA) and one-click demo login."""

from collections.abc import Callable, Iterator

import jwt
import pytest
from fastapi.testclient import TestClient

from seed.demo_data import ACCOUNTS
from src.core.config import Settings
from src.main import create_app
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.helpers import bearer, create_schema
from tests.identity.conftest import DEMO_PASSWORD

Login = Callable[[str, str], str]


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """Demo data on startup; one-click login keeps its default (off)."""
    return settings.model_copy(update={"seed_demo_data": True, "demo_password": DEMO_PASSWORD})


@pytest.fixture
def demo_client(settings: Settings) -> Iterator[TestClient]:
    """The same demo data with DEMO_LOGIN_ENABLED=true."""
    create_schema(settings.database_url)
    with TestClient(create_app(settings.model_copy(update={"demo_login_enabled": True}))) as c:
        yield c


def as_typed(phone: str) -> str:
    """'+79990000001' -> '8 (999) 000-00-01'."""
    digits = phone.removeprefix("+7")
    return f"8 ({digits[:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:]}"


def claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


# --- seeded accounts ----------------------------------------------------------------------


def test_every_demo_account_logs_in_by_email_and_phone(client: TestClient, login: Login) -> None:
    for demo in ACCOUNTS:
        assert demo.phone is not None
        for value in (demo.email, demo.phone, as_typed(demo.phone)):
            me = client.get("/me", headers=bearer(login(value, DEMO_PASSWORD))).json()
            assert me["email"] == demo.email, value
            assert me["role"]["name"] == demo.identity_role


def test_client_token_carries_org_member(login: Login) -> None:
    token = claims(login("owner@romashka.test", DEMO_PASSWORD))

    assert token["policies"]["requests.read"] == ["org_member"]
    assert token["policies"]["organizations.read"] == ["org_member"]
    assert {"requests.create", "feed.read", "assistant.use"} <= set(token["permissions"])
    assert "tasks.read" not in token["permissions"]


def test_underwriter_token_has_no_policies(login: Login) -> None:
    token = claims(login("underwriter@bank.test", DEMO_PASSWORD))

    assert token["policies"] == {}
    assert {"requests.read", "tasks.update", "decisions.read", "assistant.use"} <= set(
        token["permissions"]
    )
    assert "requests.create" not in token["permissions"]


# --- demo login ---------------------------------------------------------------------------


def test_demo_login_is_off_by_default(client: TestClient, login: Login) -> None:
    response = client.post("/auth/demo-login", json={"login": "owner@romashka.test"})

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert client.get("/auth/demo-accounts").status_code == 404
    # the account itself is there: it's the flag that closes the door
    assert login("owner@romashka.test", DEMO_PASSWORD)


def test_demo_login_issues_a_token(demo_client: TestClient) -> None:
    response = demo_client.post("/auth/demo-login", json={"login": "owner@romashka.test"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    me = demo_client.get("/me", headers=bearer(body["access_token"])).json()
    assert me["email"] == "owner@romashka.test"
    assert me["policies"]["requests.read"] == ["org_member"]


def test_demo_login_by_phone(demo_client: TestClient) -> None:
    response = demo_client.post("/auth/demo-login", json={"login": "8 (999) 000-01-01"})

    assert response.status_code == 200, response.text
    me = demo_client.get("/me", headers=bearer(response.json()["access_token"])).json()
    assert me["role"]["name"] == "underwriter"


@pytest.mark.parametrize("login", ["nobody@romashka.test", "+79990009999", "x"])
def test_demo_login_is_only_for_demo_accounts(demo_client: TestClient, login: str) -> None:
    response = demo_client.post("/auth/demo-login", json={"login": login})
    assert response.status_code == 404


@pytest.mark.parametrize("login", [ADMIN_EMAIL, ADMIN_EMAIL.upper()])
def test_bootstrap_admin_demo_logs_in(demo_client: TestClient, login: str) -> None:
    response = demo_client.post("/auth/demo-login", json={"login": login})

    assert response.status_code == 200, response.text
    me = demo_client.get("/me", headers=bearer(response.json()["access_token"])).json()
    assert me["email"] == ADMIN_EMAIL
    assert me["role"]["name"] == "admin"


def test_admin_demo_login_is_off_by_default(client: TestClient) -> None:
    assert client.post("/auth/demo-login", json={"login": ADMIN_EMAIL}).status_code == 404


def test_deleted_demo_account_cannot_demo_login(demo_client: TestClient) -> None:
    admin = demo_client.post(
        "/auth/login", json={"login": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    ).json()["access_token"]
    accounts = demo_client.get("/accounts", headers=bearer(admin)).json()
    zakat = next(a for a in accounts if a["email"] == "owner@zakat.test")
    assert demo_client.delete(f"/accounts/{zakat['id']}", headers=bearer(admin)).status_code == 204

    response = demo_client.post("/auth/demo-login", json={"login": "owner@zakat.test"})

    assert response.status_code == 404
    listed = {a["login"] for a in demo_client.get("/auth/demo-accounts").json()}
    assert "owner@zakat.test" not in listed


def test_demo_accounts_list(demo_client: TestClient) -> None:
    response = demo_client.get("/auth/demo-accounts")

    assert response.status_code == 200
    items = response.json()
    assert [item["login"] for item in items] == [demo.email for demo in ACCOUNTS] + [ADMIN_EMAIL]
    for item in items:
        assert set(item) == {"login", "phone", "role", "caption", "full_name"}
    assert DEMO_PASSWORD not in response.text
    assert items[0] == {
        "login": "owner@romashka.test",
        "phone": "+79990000001",
        "role": "client",
        "caption": "Директор ООО «Ромашка»",
        "full_name": "Смирнова Анна Сергеевна",
    }
    assert items[-2]["role"] == "underwriter"
    assert items[-2]["full_name"] == "Андеррайтеров Андрей"
    assert items[-1] == {
        "login": ADMIN_EMAIL,
        "phone": None,
        "role": "admin",
        "caption": "Администратор",
        "full_name": "Admin Admin",
    }


@pytest.mark.parametrize("email", ["owner@romashka.test", "underwriter@bank.test"])
def test_profile_lists_the_assistant_right(client: TestClient, login: Login, email: str) -> None:
    me = client.get("/me", headers=bearer(login(email, DEMO_PASSWORD))).json()

    assert "assistant.use" in me["permissions"]
